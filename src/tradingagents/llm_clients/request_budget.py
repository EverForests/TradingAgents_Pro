"""Atomic per-run model dispatch budget.

Requirement NFR-01, Invariant INV-02, Contract C4, ADR-001.
Owner module: ``tradingagents/llm_clients/request_budget.py``,
Contract C4 v1.0 (interface-v1.0).

Traceability
------------
- Requirement NFR-01: one configurable shared limit on the *actual* model
  requests made within a single main analysis flow.
- Invariant INV-02: requests in the metered scope never exceed the run's
  configured limit, including under concurrent dispatch.
- Contract C4: atomic per-run model dispatch (reserve -> charge at the outbound
  boundary -> send exactly once; typed refusals, never a fabricated decision).

Semantics
---------
- Counters are run-local to one :class:`RequestBudget` instance. There is no
  unmetered mode: ``limit`` must always be a positive integer.
- ``try_reserve()`` atomically checks and reserves one slot. A ``Reservation`` is
  the opaque C4 record ``(reservation_id, run_id, state)``.
- ``charge_attempt()`` moves a held slot to a charged attempt at the outbound
  boundary. The attempt starts in unknown delivery until the send outcome is
  known, so an ambiguous provider error is never refunded.
- ``cancel_before_send()`` releases only a slot proven unsent; a charged ticket
  can never be refunded.
- ``dispatch()`` validates C5 first, then reserves, charges, sends once and
  marks confirmed delivery.
- Historical reconciliation is out of scope. Resume is disabled: a restarted
  run uses a new ``run_id`` and starts at zero, and there is deliberately no
  restore/reset/refill/renew API at module or instance level.

Standard library only (``threading``, ``typing``, ``uuid``): no network, no
provider client, no implicit retries.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "BudgetExhausted",
    "BudgetSnapshot",
    "ContextTooLarge",
    "ProviderFailure",
    "RequestBudget",
    "Reservation",
    "dispatch",
]

_READY: Final = "READY"
_RESERVED: Final = "reserved"
_CHARGED: Final = "charged"
_CANCELLED: Final = "cancelled"


class BudgetExhausted(RuntimeError):
    """No slot available in this run (NFR-01 / INV-02, C4)."""

    code: str = "BUDGET_EXHAUSTED"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = type(self).code


class ContextTooLarge(RuntimeError):
    """C5 rejected the prepared context, before any reservation (C4/C5)."""

    code: str = "CONTEXT_TOO_LARGE"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = type(self).code


class ProviderFailure(RuntimeError):
    """Sender raised after the attempt was charged; delivery is unknown (C4)."""

    code: str = "PROVIDER_FAILURE"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = type(self).code


@dataclass(frozen=True, slots=True)
class Reservation:
    """Opaque C4 reservation record; other features must not interpret it."""

    reservation_id: str
    run_id: str
    state: str = field(default=_RESERVED)


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    """Immutable C4 view of one run's counters."""

    run_id: str
    limit: int
    charged_attempts: int
    known_sends: int
    unknown_delivery: int
    active_reservations: int
    exhausted: bool


class RequestBudget:
    """Atomic per-run request counter (NFR-01 / INV-02, C4)."""

    __slots__ = (
        "_run_id",
        "_limit",
        "_charged_attempts",
        "_known_sends",
        "_unknown_delivery",
        "_active_reservations",
        "_reservations",
        "_lock",
    )

    def __init__(self, run_id: str, limit: int | None = None) -> None:
        if not isinstance(run_id, str) or isinstance(run_id, bool) or not run_id:
            raise ValueError(f"run_id must be a non-empty str, got {run_id!r}")
        if limit is None:
            raise ValueError("limit is required: a missing limit is invalid (no unlimited mode)")
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError(f"limit must be a positive int, got {type(limit).__name__}: {limit!r}")
        if limit <= 0:
            raise ValueError(f"limit must be a positive int, got {limit!r}")

        self._run_id = run_id
        self._limit = limit
        self._charged_attempts = 0
        self._known_sends = 0
        self._unknown_delivery = 0
        self._active_reservations = 0
        # Lock-protected map from reservation_id to current state.
        self._reservations: dict[str, str] = {}
        self._lock = threading.Lock()

    def try_reserve(self) -> Reservation | None:
        """Reserve one slot, or return ``None`` when the run is at its limit."""
        with self._lock:
            if self._charged_attempts + self._active_reservations >= self._limit:
                return None
            reservation_id = f"{self._run_id}:{uuid.uuid4().hex}"
            self._reservations[reservation_id] = _RESERVED
            self._active_reservations += 1
            return Reservation(reservation_id=reservation_id, run_id=self._run_id, state=_RESERVED)

    def charge_attempt(self, ticket: Reservation) -> None:
        """Convert this budget's held reservation into a charged attempt.

        The attempt enters unknown delivery: only :func:`dispatch` can later
        mark a confirmed send.
        """
        with self._lock:
            self._require_reserved(ticket, _CHARGED)
            self._reservations[ticket.reservation_id] = _CHARGED
            self._active_reservations -= 1
            self._charged_attempts += 1
            self._unknown_delivery += 1

    def cancel_before_send(self, ticket: Reservation) -> None:
        """Release a slot proven unsent; idempotent while still cancelled."""
        with self._lock:
            state = self._state_of(ticket)
            if state == _CANCELLED:
                return
            if state == _CHARGED:
                raise RuntimeError(
                    f"reservation {ticket.reservation_id!r} was already charged and cannot be released"
                )
            if state != _RESERVED:
                raise RuntimeError(f"reservation {ticket.reservation_id!r} is not cancellable")
            self._reservations[ticket.reservation_id] = _CANCELLED
            self._active_reservations -= 1

    def snapshot(self) -> BudgetSnapshot:
        """Atomically read an immutable view of the run counters."""
        with self._lock:
            return BudgetSnapshot(
                run_id=self._run_id,
                limit=self._limit,
                charged_attempts=self._charged_attempts,
                known_sends=self._known_sends,
                unknown_delivery=self._unknown_delivery,
                active_reservations=self._active_reservations,
                exhausted=self._charged_attempts + self._active_reservations >= self._limit,
            )

    def _state_of(self, ticket: Reservation) -> str:
        """Look up a ticket's current state; reject foreign tickets. Caller locks."""
        if not isinstance(ticket, Reservation):
            raise TypeError(f"expected a Reservation, got {type(ticket).__name__}")
        if ticket.run_id != self._run_id:
            raise ValueError(f"reservation {ticket.reservation_id!r} belongs to another run")
        state = self._reservations.get(ticket.reservation_id)
        if state is None:
            raise ValueError(f"reservation {ticket.reservation_id!r} is unknown to this budget")
        return state

    def _require_reserved(self, ticket: Reservation, target: str) -> None:
        """Raise unless the ticket is a held reservation. Caller locks."""
        state = self._state_of(ticket)
        if state != _RESERVED:
            raise RuntimeError(
                f"reservation {ticket.reservation_id!r} is {state!r}, expected 'reserved' before {target}"
            )

    def _mark_delivered(self, ticket: Reservation) -> None:
        """Record a confirmed send for a charged attempt (C4 identity)."""
        with self._lock:
            if self._state_of(ticket) != _CHARGED:
                raise RuntimeError(f"reservation {ticket.reservation_id!r} is not a charged attempt")
            if self._unknown_delivery <= 0:
                raise RuntimeError(f"run {self._run_id!r} has no unknown-delivery attempt to confirm")
            self._unknown_delivery -= 1
            self._known_sends += 1


def dispatch(prepared: Any, budget: RequestBudget, send: Callable[[Any], Any]) -> Any:
    """Send one prepared request through the C4 boundary and return the response.

    Order is fixed: C5 status check, reserve, charge, send once, confirm. A
    refusal raises a typed failure and never returns a decision of its own.
    """
    if not isinstance(budget, RequestBudget):
        raise TypeError(f"budget must be a RequestBudget, got {type(budget).__name__}")
    if not callable(send):
        raise TypeError(f"send must be callable, got {type(send).__name__}")
    if getattr(prepared, "status", None) != _READY:
        raise ContextTooLarge("prepared context is not READY; nothing was reserved or sent")

    ticket = budget.try_reserve()
    if ticket is None:
        snapshot = budget.snapshot()
        raise BudgetExhausted(
            f"run {snapshot.run_id!r} reached its limit of {snapshot.limit} attempts; "
            "no request was sent"
        )

    budget.charge_attempt(ticket)
    payload = getattr(prepared, "messages", prepared)
    try:
        response = send(payload)
    except Exception as exc:
        raise ProviderFailure(
            f"send attempt for run {budget.snapshot().run_id!r} failed after charging; "
            "delivery is unknown"
        ) from exc

    budget._mark_delivered(ticket)  # noqa: SLF001 - owner-internal confirmation
    return response
