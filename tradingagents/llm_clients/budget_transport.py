"""Metered HTTP transport for the C4 budget and the C5 scoped call sites.

Requirements NFR-01 (per-run request budget) and NFR-02 (bounded scoped
context); invariant INV-02; contracts C4 ``dispatch`` and C5
``canonical_message_bytes``; ADR-001.

Owner module: ``tradingagents/llm_clients/budget_transport.py``.

Placement
---------
The unit of accounting is the *actual outbound model request*. The only place
where every OpenAI-compatible tier request is observable exactly once is the
HTTP transport underneath the SDK, so metering, the C5 size check and the
retry suppression live here rather than in per-agent call sites:

- :func:`budgeted_http_client` builds the ``httpx.Client`` handed to the SDK.
  Its transport wraps a plain ``httpx.HTTPTransport(retries=0)`` so an SDK or
  transport retry can never produce a second, unmetered request (INV-02).
- :func:`request_budget_scope` publishes the run's :class:`RequestBudget` in a
  ``ContextVar`` for the duration of one analysis flow. Outside an active
  scope (settlement/reflection after the run, or any non-run use) the
  transport delegates normally and meters nothing.
- :func:`scoped_context_limit` marks the two NFR-02 call sites (analyst
  closure, neutral-risk). Only marked calls are measured against the C5 cap
  before dispatch; unmarked calls keep their existing behavior.

Ordering (INV-02): the C5 measurement happens *before* the C4 reservation, so
an oversized request is refused with zero reservation, zero debit and zero
send, mirroring :func:`request_budget.dispatch`, which re-checks the prepared
status.

Failure mapping for the graph (:func:`terminal_request_status`) inspects the
exception's ``__cause__``/``__context__`` chain under a loop guard so a caller
sees ``BUDGET_EXHAUSTED``, ``CONTEXT_TOO_LARGE``, ``FAILED`` or ``None``
without parsing prose. Model output is never trusted here: the transport only
counts, measures and delegates.

Standard library plus ``httpx`` (already a transitive dependency of the OpenAI
SDK); no new dependency is introduced.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from contextvars import ContextVar, Token
from typing import Any, Final

import httpx

from . import context_limit, request_budget

__all__ = [
    "BUDGETED_TRANSPORT",
    "budgeted_http_client",
    "request_budget_scope",
    "scoped_context_limit",
    "terminal_request_status",
]

# C0 terminal execution states produced by this module.
BUDGET_EXHAUSTED: Final = "BUDGET_EXHAUSTED"
CONTEXT_TOO_LARGE: Final = "CONTEXT_TOO_LARGE"
FAILED: Final = "FAILED"

# Marker used by ``create_tier_client`` to tell a budgeted client apart from a
# plain ``http_client`` forwarded by a caller.
BUDGETED_TRANSPORT: Final = "budgeted"

_ACTIVE_BUDGET: ContextVar[request_budget.RequestBudget | None] = ContextVar(
    "tradingagents_active_request_budget", default=None
)
_IN_SCOPED_CALL: ContextVar[bool] = ContextVar(
    "tradingagents_in_scoped_context_call", default=False
)

# Error kinds ranked lowest first; when an exception chain carries several, the
# outermost (closest to the caller) wins, so exact ordering of classification is
# stable regardless of how many wrappers the SDK adds.
_ERROR_KINDS: Final = ("provider", "context", "budget")


# --- run scope --------------------------------------------------------------


@contextlib.contextmanager
def request_budget_scope(
    budget: request_budget.RequestBudget | None,
) -> Iterator[request_budget.RequestBudget | None]:
    """Publish ``budget`` as the active run budget for the enclosed block.

    Nested scopes stack (each exit restores the previous value). ``None``
    disables metering for the block, which is the settlement/out-of-run state.
    """

    if budget is not None and not isinstance(budget, request_budget.RequestBudget):
        raise TypeError(f"budget must be a RequestBudget or None, got {type(budget).__name__}")
    token: Token = _ACTIVE_BUDGET.set(budget)
    try:
        yield budget
    finally:
        _ACTIVE_BUDGET.reset(token)


@contextlib.contextmanager
def scoped_context_limit() -> Iterator[None]:
    """Mark one C5 scoped call site for the C5 size check.

    Applies to the analyst-closure and neutral-risk call sites. Requests made
    inside this block are measured with
    :func:`context_limit.canonical_message_bytes` against
    ``context_limit.DEFAULT_MAX_MESSAGE_BYTES`` before any dispatch.
    """

    token: Token = _IN_SCOPED_CALL.set(True)
    try:
        yield
    finally:
        _IN_SCOPED_CALL.reset(token)


def active_budget() -> request_budget.RequestBudget | None:
    """The run budget in effect for the current context, if any."""
    return _ACTIVE_BUDGET.get()


# --- terminal failure mapping ----------------------------------------------


def _is_budget_exhausted(exc: BaseException) -> bool:
    return isinstance(exc, request_budget.BudgetExhausted) or getattr(
        exc, "code", None
    ) == request_budget.BudgetExhausted.code


def _is_context_too_large(exc: BaseException) -> bool:
    # Both owner-module classes are accepted: ``request_budget`` raises its own
    # C4-before-send refusal and ``context_limit`` raises the per-site class
    # with ``message_bytes``/``mandatory_bytes``/``max_message_bytes``.
    if isinstance(exc, (request_budget.ContextTooLarge, context_limit.ContextTooLarge)):
        return True
    code = getattr(exc, "code", None) or getattr(exc, "reason_code", None)
    return code in (request_budget.ContextTooLarge.code, context_limit.CONTEXT_TOO_LARGE)


def _is_provider_failure(exc: BaseException) -> bool:
    return isinstance(exc, request_budget.ProviderFailure) or getattr(
        exc, "code", None
    ) == request_budget.ProviderFailure.code


def terminal_request_status(exc: BaseException | None) -> str | None:
    """C0 terminal state implied by ``exc``, or ``None`` for a non-C4/C5 error.

    The exception is classified, then its ``__cause__`` / ``__context__`` chain
    is walked (loop-guarded) so a wrapper added by the SDK or graph still
    yields the typed state:

    - ``budget``  -> ``BUDGET_EXHAUSTED`` (C4)
    - ``context`` -> ``CONTEXT_TOO_LARGE`` (C4/C5)
    - ``provider``-> ``FAILED`` (C4 send failed after charging)

    Classification is by type/code only; messages are never inspected.
    """

    if exc is None:
        return None

    kinds: set[str] = set()
    seen: set[int] = set()
    pending: list[BaseException | None] = [exc]
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        if _is_budget_exhausted(current):
            kinds.add("budget")
        elif _is_context_too_large(current):
            kinds.add("context")
        elif _is_provider_failure(current):
            kinds.add("provider")
        pending.append(current.__cause__)
        pending.append(current.__context__)

    for kind in reversed(_ERROR_KINDS):
        if kind in kinds:
            return {
                "budget": BUDGET_EXHAUSTED,
                "context": CONTEXT_TOO_LARGE,
                "provider": FAILED,
            }[kind]
    return None


# --- HTTP transport ---------------------------------------------------------


def budgeted_http_client(
    *,
    timeout: float | httpx.Timeout | None = 600.0,
    max_message_bytes: int | None = None,
    **client_kwargs: Any,
) -> httpx.Client:
    """An ``httpx.Client`` whose transport meters the C4/C5 boundaries.

    * ``max_retries=0`` on the inner transport and a fresh client per SDK
      client: no transport-level retry can duplicate a metered send.
    * ``follow_redirects=False`` so one logical send is one request.

    ``client_kwargs`` are forwarded to ``httpx.Client`` (for example
    ``headers``, ``verify``, ``proxy``); ``transport``/``mounts`` are rejected
    because they would bypass the metered transport.
    """

    if "transport" in client_kwargs or "mounts" in client_kwargs:
        raise ValueError("budgeted_http_client owns its transport; do not pass 'transport'/'mounts'")
    transport = _BudgetedTransport(httpx.HTTPTransport(retries=0), max_message_bytes=max_message_bytes)
    return httpx.Client(transport=transport, follow_redirects=False, timeout=timeout, **client_kwargs)


class _BudgetedTransport(httpx.BaseTransport):
    """C4/C5 boundary over a plain HTTP transport.

    ``handle_request`` settles the request *before* calling the inner transport,
    so a response delivered by the inner transport is always a charged, counted
    send; a refusal raises without calling the inner transport at all.
    """

    def __init__(
        self,
        inner: httpx.BaseTransport,
        *,
        max_message_bytes: int | None = None,
    ) -> None:
        if max_message_bytes is None:
            max_message_bytes = context_limit.DEFAULT_MAX_MESSAGE_BYTES
        if (
            isinstance(max_message_bytes, bool)
            or not isinstance(max_message_bytes, int)
            or max_message_bytes <= 0
        ):
            raise ValueError(f"max_message_bytes must be a positive integer, got {max_message_bytes!r}")
        self._inner = inner
        self._max_message_bytes = max_message_bytes

    @property
    def inner(self) -> httpx.BaseTransport:
        return self._inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        budget = _ACTIVE_BUDGET.get()

        if budget is None:
            # Settlement / out of run: delegate, never meter (INV-02 scope).
            return self._inner.handle_request(request)

        messages = _request_messages(request)
        return request_budget.dispatch(
            self._prepare(messages),
            budget,
            lambda prepared: self._inner.handle_request(request),
        )

    def _prepare(self, messages: list[Any]) -> context_limit.PreparedRequest:
        """Size-check marked calls (C5), then build the C4-ready request."""
        if messages and _IN_SCOPED_CALL.get():
            measured = context_limit.canonical_message_bytes(messages)
            if measured > self._max_message_bytes:
                # C5 refusal before C4 reservation: zero reservation, zero
                # debit, zero send.
                raise context_limit.ContextTooLarge(
                    message_bytes=measured,
                    mandatory_bytes=measured,
                    max_message_bytes=self._max_message_bytes,
                    site="budgeted_transport",
                )
        return context_limit.nonreducing_prepared_request(messages)

    def close(self) -> None:
        self._inner.close()

    def __enter__(self) -> _BudgetedTransport:
        self._inner.__enter__()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self._inner.__exit__(*exc_info)


def _request_messages(request: httpx.Request) -> list[Any]:
    """The provider-facing ``messages`` array of an outbound JSON request.

    Uses the bytes actually about to be sent (``request.content``), not an
    earlier Python-side draft, so the measurement describes the real request.
    Returns an empty list when the body carries no message array; such a
    request is still metered but not size-checked.
    """

    body = request.content
    if not body:
        return []
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return []
    return messages
