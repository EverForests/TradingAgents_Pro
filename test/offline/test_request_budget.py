"""Offline acceptance tests for C4 v1.0 - atomic per-run model dispatch.

Traceability
------------
- Requirement NFR-01: a configurable shared limit on the *actual* model
  requests made within one stock-analysis main flow (docs/req/requirements.yaml).
- Invariant INV-02: requests in the metered analysis scope never exceed the
  run's configured call limit, including under concurrent dispatch
  (docs/architecture/invariants.md).
- Contract C4 - atomic per-run model dispatch
  (docs/architecture/interface-contracts.md, "C4" and the "V1 callable
  boundaries" table). Owner module:
  ``tradingagents/llm_clients/request_budget.py``. Planned calls:
  ``RequestBudget(run_id, limit)``, ``try_reserve()``, ``charge_attempt()``,
  ``cancel_before_send()``, ``snapshot()`` and
  ``dispatch(prepared, budget, send)``.
- ADR-001 (NFR-01 row): count dispatch at a common outbound boundary and
  atomically reserve a slot per run (docs/architecture/adr/001-choice-tbd.md).
- Runtime policy catalog NFR-01 / INV-02 and "Combined-path precedence":
  no slot -> BUDGET_EXHAUSTED, no send, no official rating; a provider error
  after an attempted send consumes the slot; a C5 CONTEXT_TOO_LARGE rejection
  happens before reservation and debits no budget
  (docs/architecture/runtime-policy-catalog.md).
- verification-constraints.md: frozen case IDs T-NFR01-BOUNDARY,
  T-NFR01-RETRY, T-NFR01-ISOLATION, T-NFR01-FAILURE, T-NFR01-RESUME and
  T-INV02-RACE. Every fit criterion has a positive control; every invariant
  has a negative test that fails if the enforcement is bypassed.

Fixture revision: nfr01-fixtures-v1 (inline, LIMIT = 3, run ids
``run-A-0001`` / ``run-B-0002``). Developer/owner: JunKai Yan.

Approved interpretations (recorded in the Gate 1 plan, not re-opened here):
OPEN-2 resume disabled (no resume/restore/reset/refill API; a restarted run
uses a new ``run_id`` and starts at zero); OPEN-3 settlement exclusion is a
static source assertion (module source never imports or references
settlement); OPEN-4 sender exception -> ``ProviderFailure`` with code
``"PROVIDER_FAILURE"`` and the original exception as ``__cause__``, slot stays
charged and ``unknown_delivery`` increments; OPEN-5 ``try_reserve()`` returns
``None`` on refusal and ``dispatch()`` converts it into ``BudgetExhausted``
(``"BUDGET_EXHAUSTED"``); OPEN-6 a second ``cancel_before_send`` is an
idempotent no-op that releases headroom at most once, cancelling a charged
ticket raises ``RuntimeError``; OPEN-7 no UNMETERED/None/unlimited mode -
``limit`` must be a positive ``int`` and ``bool`` is rejected.

Design notes
------------
* Only the module object is imported at collection time
  (``import ... as rb``); every other name is resolved inside the test body.
  While the old draft API is still installed, collection succeeds and each
  test fails at run time with an explicit traceability message.
* All fixtures are inline: LIMIT = 3, a thread-safe FakeTransport that records
  payloads/counts and can raise a synthetic OSError on a chosen call, and a
  tiny PreparedRequest stub (status READY / CONTEXT_TOO_LARGE, messages).
* Deterministic: no network, no sleeps, no clock dependence; concurrency uses
  ``threading.Barrier`` only.
* Standard library and pytest only.
"""

from __future__ import annotations

import contextlib
import threading

import pytest

import tradingagents.llm_clients.request_budget as rb

# ---------------------------------------------------------------------------
# Inline fixtures - nfr01-fixtures-v1
# ---------------------------------------------------------------------------

LIMIT = 3
RUN_A = "run-A-0001"
RUN_B = "run-B-0002"
MODULE_SOURCE = rb.__file__

SNAPSHOT_FIELDS = (
    "run_id",
    "limit",
    "charged_attempts",
    "known_sends",
    "unknown_delivery",
    "active_reservations",
    "exhausted",
)


class PreparedRequest:
    """Tiny C5 PreparedRequest stub (v1 shared record layout)."""

    def __init__(self, status: str = "READY", messages: list[dict] | None = None) -> None:
        self.status = status
        self.messages = [{"role": "user", "content": "ping"}] if messages is None else messages


class FakeTransport:
    """Thread-safe fake transport: records payloads and counts real sends.

    ``send`` records the payload and increments ``send_count`` *before* the
    optional synthetic OSError, so a failed attempt is still observable at the
    transport boundary (C4: count actual fake sends, not the reported counter).
    """

    def __init__(self, fail_on_call: int | None = None) -> None:
        self.payloads: list[object] = []
        self.send_count = 0
        self.attempts = 0
        self._fail_on_call = fail_on_call
        self._lock = threading.Lock()

    def send(self, payload: object) -> str:
        with self._lock:
            self.attempts += 1
            attempt = self.attempts
            self.send_count += 1
            self.payloads.append(payload)
            fail_now = self._fail_on_call is not None and attempt == self._fail_on_call
        if fail_now:
            raise OSError("synthetic transport failure")
        return f"response-{attempt}"


def snapshot_of(budget) -> dict:
    """Read and validate the C4 snapshot shape (exact field names)."""
    snap = budget.snapshot()
    fields = {name: getattr(snap, name, None) for name in SNAPSHOT_FIELDS}
    missing = [name for name in SNAPSHOT_FIELDS if not hasattr(snap, name)]
    assert not missing, (
        f"T-NFR01-BOUNDARY/C4: snapshot() must expose {missing}; "
        f"got attributes {sorted(dir(snap))}"
    )
    assert snap.charged_attempts == snap.known_sends + snap.unknown_delivery, (
        "C4 identity charged_attempts == known_sends + unknown_delivery "
        f"violated: {fields}"
    )
    assert snap.charged_attempts + snap.active_reservations <= snap.limit, (
        "C4 identity charged_attempts + active_reservations <= limit "
        f"violated: {fields}"
    )
    return fields


def make_budget(run_id: str = RUN_A, limit: int = LIMIT):
    return rb.RequestBudget(run_id=run_id, limit=limit)


def dispatch_ok(budget, transport: FakeTransport, prepared=None):
    prepared = PreparedRequest() if prepared is None else prepared
    return rb.dispatch(prepared, budget, transport.send)


def assert_no_official_rating(outcome, case_id: str) -> None:
    """A refusal must never surface a rating/Hold/default recommendation."""
    assert outcome is None, (
        f"{case_id}: a refused dispatch must not return a recommendation, got {outcome!r}"
    )


def assert_no_rating_in_exception(exc: BaseException, case_id: str) -> None:
    text = repr(exc) + " " + str(exc)
    for banned in ("Hold", "Buy", "Sell", "rating"):
        assert banned.lower() not in text.lower(), (
            f"{case_id}: typed failure must not carry a {banned!r} decision: {text!r}"
        )


# ---------------------------------------------------------------------------
# T-NFR01-BOUNDARY - limit 3, exactly three sends, fourth typed refusal
# ---------------------------------------------------------------------------


def test_t_nfr01_boundary_limit_three_sends_three():
    """T-NFR01-BOUNDARY: NFR-01/INV-02/C4 - limit 3 allows exactly 3 attempts."""
    budget = make_budget()
    transport = FakeTransport()

    responses = [dispatch_ok(budget, transport) for _ in range(LIMIT)]

    assert transport.send_count == LIMIT, "limit 3 must allow exactly three sends"
    assert len(responses) == LIMIT, "each dispatched attempt returns the sender response"
    snap = snapshot_of(budget)
    assert snap["run_id"] == RUN_A
    assert snap["limit"] == LIMIT
    assert snap["charged_attempts"] == LIMIT
    assert snap["known_sends"] == LIMIT
    assert snap["unknown_delivery"] == 0
    assert snap["active_reservations"] == 0
    assert snap["exhausted"] is True


def test_t_nfr01_boundary_fourth_dispatch_is_refused_without_send():
    """T-NFR01-BOUNDARY: NFR-01/INV-02/C4 - the 4th attempt is refused, not sent."""
    budget = make_budget()
    transport = FakeTransport()
    for _ in range(LIMIT):
        dispatch_ok(budget, transport)
    sends_before = transport.send_count

    with pytest.raises(rb.BudgetExhausted) as excinfo:
        dispatch_ok(budget, transport)

    assert transport.send_count == sends_before, "the 4th attempt must not send"
    assert sends_before == LIMIT
    assert getattr(excinfo.value, "code", None) == "BUDGET_EXHAUSTED"
    assert_no_rating_in_exception(excinfo.value, "T-NFR01-BOUNDARY")


def test_t_nfr01_boundary_try_reserve_returns_none_and_dispatch_raises():
    """T-NFR01-BOUNDARY: OPEN-5 - try_reserve() returns None; dispatch raises."""
    budget = make_budget()
    transport = FakeTransport()
    for _ in range(LIMIT):
        dispatch_ok(budget, transport)

    assert budget.try_reserve() is None, "OPEN-5: refusal is signalled by None"
    snap = snapshot_of(budget)
    assert snap["active_reservations"] == 0, "a refused reservation must not be counted"
    assert snap["exhausted"] is True

    with pytest.raises(rb.BudgetExhausted):
        dispatch_ok(budget, transport)
    assert transport.send_count == LIMIT


def test_t_nfr01_boundary_budget_exhausted_is_typed_failure():
    """T-NFR01-BOUNDARY: NFR-01/C4 - refusal is the typed BudgetExhausted failure."""
    budget = make_budget()
    transport = FakeTransport()
    for _ in range(LIMIT):
        dispatch_ok(budget, transport)
    with pytest.raises(rb.BudgetExhausted):
        dispatch_ok(budget, transport)
    assert hasattr(rb, "ProviderFailure"), "C4 requires a typed ProviderFailure owner type"
    assert hasattr(rb, "BudgetExhausted"), "C4 requires a typed BudgetExhausted owner type"


def test_t_nfr01_boundary_exhaustion_is_sticky():
    """T-NFR01-BOUNDARY: INV-02 - repeated refusals never let a send through."""
    budget = make_budget()
    transport = FakeTransport()
    for _ in range(LIMIT):
        dispatch_ok(budget, transport)
    for _ in range(3):
        with pytest.raises(rb.BudgetExhausted):
            dispatch_ok(budget, transport)
    assert transport.send_count == LIMIT
    assert snapshot_of(budget)["charged_attempts"] == LIMIT


# ---------------------------------------------------------------------------
# Limit / run_id validation (OPEN-7: positive int only, no unmetered mode)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_limit", [0, -1, True, 2.5, "3", None])
def test_t_nfr01_boundary_invalid_limit_rejected(bad_limit):
    """T-NFR01-BOUNDARY: OPEN-7/C4 - limit must be a positive int (bool rejected)."""
    with pytest.raises(ValueError):
        rb.RequestBudget(run_id=RUN_A, limit=bad_limit)


def test_t_nfr01_boundary_no_unmetered_mode_exists():
    """T-NFR01-BOUNDARY: OPEN-7 - no UNMETERED sentinel or unlimited path."""
    assert not hasattr(rb, "UNMETERED"), "OPEN-7: UNMETERED mode is not approved"
    with pytest.raises(ValueError):
        rb.RequestBudget(run_id=RUN_A)


def test_t_nfr01_boundary_empty_run_id_rejected():
    """T-NFR01-BOUNDARY: C0/C4 - every authoritative record carries a run_id."""
    for bad_run_id in ("", None):
        with pytest.raises(ValueError):
            rb.RequestBudget(run_id=bad_run_id, limit=LIMIT)


def test_t_nfr01_boundary_refusal_surfaces_no_rating():
    """T-NFR01-BOUNDARY: NFR-01/C4 - refusal returns no rating/Hold/default value."""
    budget = make_budget()
    transport = FakeTransport()
    for _ in range(LIMIT):
        dispatch_ok(budget, transport)

    # dispatch() raises instead of returning a placeholder recommendation.
    outcome = None
    with contextlib.suppress(rb.BudgetExhausted):
        outcome = dispatch_ok(budget, transport)
    assert_no_official_rating(outcome, "T-NFR01-BOUNDARY")
    assert transport.send_count == LIMIT


def test_t_nfr01_boundary_snapshot_field_names_are_exact():
    """T-NFR01-BOUNDARY: C4 - snapshot exposes the v1 field names exactly."""
    budget = make_budget()
    snap = budget.snapshot()
    for name in SNAPSHOT_FIELDS:
        assert hasattr(snap, name), f"C4 snapshot must expose {name!r}"
    assert not hasattr(snap, "remaining"), "C4 does not define a remaining() snapshot field"


# ---------------------------------------------------------------------------
# T-NFR01-RETRY - application retries/fallback are separate charged attempts
# ---------------------------------------------------------------------------


def test_t_nfr01_retry_each_application_retry_is_a_charged_attempt():
    """T-NFR01-RETRY: NFR-01/C4 - structured->fallback retries each cost a slot."""
    budget = make_budget()
    transport = FakeTransport()

    # One logical node, three outgoing attempts (structured, fallback, retry).
    for _ in range(LIMIT):
        dispatch_ok(budget, transport)

    assert transport.send_count == LIMIT, "application retries are separate outgoing attempts"
    snap = snapshot_of(budget)
    assert snap["charged_attempts"] == LIMIT
    assert snap["known_sends"] == LIMIT

    with pytest.raises(rb.BudgetExhausted):
        dispatch_ok(budget, transport)  # a fourth retry is refused
    assert transport.send_count == LIMIT


def test_t_nfr01_retry_retry_after_failure_consumes_another_slot():
    """T-NFR01-RETRY: C4 - a retry after a failed attempt needs a new slot."""
    budget = make_budget()
    transport = FakeTransport(fail_on_call=1)

    with pytest.raises(rb.ProviderFailure):
        dispatch_ok(budget, transport)
    assert transport.send_count == 1

    # Application retry is a distinct charged attempt.
    dispatch_ok(budget, transport)
    assert transport.send_count == 2
    snap = snapshot_of(budget)
    assert snap["charged_attempts"] == 2
    assert snap["known_sends"] == 1
    assert snap["unknown_delivery"] == 1


def test_t_nfr01_retry_transport_send_is_invoked_once_per_dispatch():
    """T-NFR01-RETRY: C4 - dispatch invokes send exactly once (no SDK retries)."""
    budget = make_budget()
    transport = FakeTransport()
    for _ in range(LIMIT):
        dispatch_ok(budget, transport)
    assert transport.attempts == LIMIT, "no implicit transport-level retries"
    assert transport.payloads[0] is not None


# ---------------------------------------------------------------------------
# T-NFR01-ISOLATION - concurrent runs do not share counters
# ---------------------------------------------------------------------------


def test_t_nfr01_isolation_two_runs_have_independent_counters():
    """T-NFR01-ISOLATION: NFR-01/C4 - counters are run-local."""
    run_a, run_b = make_budget(RUN_A), make_budget(RUN_B)
    transport = FakeTransport()
    dispatch_ok(run_a, transport)
    dispatch_ok(run_a, transport)
    dispatch_ok(run_b, transport)

    snap_a = snapshot_of(run_a)
    snap_b = snapshot_of(run_b)
    assert snap_a["run_id"] == RUN_A and snap_b["run_id"] == RUN_B
    assert snap_a["charged_attempts"] == 2
    assert snap_b["charged_attempts"] == 1


def test_t_nfr01_isolation_exhausted_run_does_not_block_fresh_run():
    """T-NFR01-ISOLATION: INV-02 - an exhausted run never blocks a new run."""
    transport = FakeTransport()
    run_a = make_budget(RUN_A)
    for _ in range(LIMIT):
        dispatch_ok(run_a, transport)
    assert snapshot_of(run_a)["exhausted"] is True

    run_b = make_budget(RUN_B)
    for _ in range(LIMIT):
        dispatch_ok(run_b, transport)
    assert transport.send_count == 2 * LIMIT
    assert snapshot_of(run_b)["charged_attempts"] == LIMIT
    assert snapshot_of(run_a)["charged_attempts"] == LIMIT


def test_t_nfr01_isolation_concurrent_runs_are_thread_safe():
    """T-NFR01-ISOLATION: INV-02 - two threads, one per run, never share slots."""
    transport = FakeTransport()
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker(run):
        try:
            barrier.wait(timeout=10)
            for _ in range(LIMIT):
                dispatch_ok(run, transport)
            with pytest.raises(rb.BudgetExhausted):
                dispatch_ok(run, transport)
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    run_a, run_b = make_budget(RUN_A), make_budget(RUN_B)
    threads = [threading.Thread(target=worker, args=(r,)) for r in (run_a, run_b)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, f"unexpected worker errors: {errors!r}"
    assert transport.send_count == 2 * LIMIT
    assert snapshot_of(run_a)["charged_attempts"] == LIMIT
    assert snapshot_of(run_b)["charged_attempts"] == LIMIT


def test_t_nfr01_isolation_reservation_occupies_headroom():
    """T-NFR01-ISOLATION: C4 - charged + active reservations never exceed limit."""
    budget = make_budget()
    transport = FakeTransport()
    ticket = budget.try_reserve()
    assert ticket is not None, "first reservation must succeed under limit 3"
    snap = snapshot_of(budget)
    assert snap["active_reservations"] == 1
    assert snap["charged_attempts"] == 0

    # Two more dispatches fill the remaining two slots; the reservation still
    # holds the third, so charged(2) + reserved(1) == limit and a further
    # dispatch is refused even though only two sends have happened.
    dispatch_ok(budget, transport)
    dispatch_ok(budget, transport)
    assert transport.send_count == 2
    with pytest.raises(rb.BudgetExhausted):
        dispatch_ok(budget, transport)
    assert transport.send_count == 2, "the held reservation must block a third send"
    snap = snapshot_of(budget)
    assert snap["active_reservations"] == 1
    assert snap["charged_attempts"] + snap["active_reservations"] == LIMIT


# ---------------------------------------------------------------------------
# T-NFR01-FAILURE - ambiguous provider failure keeps the slot charged
# ---------------------------------------------------------------------------


def test_t_nfr01_failure_sender_exception_raises_provider_failure():
    """T-NFR01-FAILURE: OPEN-4 - sender error -> typed ProviderFailure."""
    budget = make_budget()
    transport = FakeTransport(fail_on_call=1)

    with pytest.raises(rb.ProviderFailure) as excinfo:
        dispatch_ok(budget, transport)

    assert getattr(excinfo.value, "code", None) == "PROVIDER_FAILURE"
    assert isinstance(excinfo.value.__cause__, OSError), (
        "OPEN-4: the original exception must be preserved as __cause__"
    )
    assert transport.send_count == 1, "the attempt reached the transport"


def test_t_nfr01_failure_slot_stays_charged_and_unknown_delivery_set():
    """T-NFR01-FAILURE: C4/OPEN-4 - ambiguous send stays charged, unknown_delivery=1."""
    budget = make_budget()
    transport = FakeTransport(fail_on_call=1)
    with pytest.raises(rb.ProviderFailure):
        dispatch_ok(budget, transport)

    snap = snapshot_of(budget)
    assert snap["charged_attempts"] == 1, "an ambiguous send must not be refunded"
    assert snap["known_sends"] == 0
    assert snap["unknown_delivery"] == 1
    assert snap["active_reservations"] == 0


def test_t_nfr01_failure_following_dispatch_still_works_until_exhausted():
    """T-NFR01-FAILURE: C4 - the failure consumed a real slot."""
    budget = make_budget()
    transport = FakeTransport(fail_on_call=1)
    with pytest.raises(rb.ProviderFailure):
        dispatch_ok(budget, transport)
    # limit 3, one ambiguous attempt -> exactly two more sends allowed.
    dispatch_ok(budget, transport)
    dispatch_ok(budget, transport)
    assert transport.send_count == 3
    with pytest.raises(rb.BudgetExhausted):
        dispatch_ok(budget, transport)
    assert transport.send_count == 3


def test_t_nfr01_failure_ambiguous_send_never_refunded_by_reset():
    """T-NFR01-FAILURE: C4 - a failed attempt cannot be refunded or re-sent."""
    budget = make_budget()
    transport = FakeTransport(fail_on_call=1)
    with pytest.raises(rb.ProviderFailure):
        dispatch_ok(budget, transport)
    for name in ("reset", "restore", "refill", "renew", "release"):
        assert not hasattr(budget, name), f"no {name}() may refund a failed attempt"


def test_t_nfr01_failure_provider_failure_carries_no_rating():
    """T-NFR01-FAILURE: NFR-01/C0 - a provider failure never yields a rating."""
    budget = make_budget()
    transport = FakeTransport(fail_on_call=1)
    with pytest.raises(rb.ProviderFailure) as excinfo:
        dispatch_ok(budget, transport)
    assert_no_rating_in_exception(excinfo.value, "T-NFR01-FAILURE")


# ---------------------------------------------------------------------------
# T-NFR01-RESUME - resume disabled; a restarted run is a new run_id
# ---------------------------------------------------------------------------


def test_t_nfr01_resume_no_resume_or_reset_api():
    """T-NFR01-RESUME: OPEN-2/C0 - no resume/restore/reset/refill on module or run."""
    for name in ("resume", "restore", "reset", "refill", "renew"):
        assert not hasattr(rb, name), f"module must not expose {name}()"
        assert not hasattr(make_budget(), name), f"budget must not expose {name}()"


def test_t_nfr01_resume_restart_uses_new_run_id_and_starts_at_zero():
    """T-NFR01-RESUME: OPEN-2/C4 - a restarted run starts fresh under a new run_id."""
    transport = FakeTransport()
    run_a = make_budget(RUN_A)
    for _ in range(LIMIT):
        dispatch_ok(run_a, transport)
    with pytest.raises(rb.BudgetExhausted):
        dispatch_ok(run_a, transport)

    run_b = make_budget(RUN_B)
    snap_b = snapshot_of(run_b)
    assert snap_b["charged_attempts"] == 0, "a new run starts at zero, not resumed"
    assert snap_b["run_id"] == RUN_B
    assert snap_b["exhausted"] is False
    dispatch_ok(run_b, transport)
    assert transport.send_count == LIMIT + 1


def test_t_nfr01_resume_same_run_id_never_restores_spent_count():
    """T-NFR01-RESUME: INV-02 - re-using a run_id does not resume its counter."""
    # Two separate instances: there is no shared store, so the same run_id
    # gets a fresh local counter (resume disabled). The invariant we test is
    # that no API exists to restore the *old* instance's spent count.
    run_a = make_budget(RUN_A)
    transport = FakeTransport()
    for _ in range(LIMIT):
        dispatch_ok(run_a, transport)
    restored = make_budget(RUN_A)
    assert snapshot_of(restored)["charged_attempts"] == 0
    assert snapshot_of(run_a)["charged_attempts"] == LIMIT, "old instance stays exhausted"


def test_t_nfr01_resume_no_settlement_coupling_in_module_source():
    """T-NFR01-RESUME: OPEN-3/C4 - settlement is excluded from the module source."""
    with open(MODULE_SOURCE, encoding="utf-8") as handle:
        source = handle.read().lower()
    assert "settlement" not in source, "C4 excludes historical settlement from metering"
    assert "settle" not in source, "C4 excludes historical settlement from metering"


# ---------------------------------------------------------------------------
# C5-first: CONTEXT_TOO_LARGE obtains no reservation and no debit
# ---------------------------------------------------------------------------


def test_t_nfr01_boundary_context_too_large_yields_zero_sends_and_no_debit():
    """T-NFR01-BOUNDARY: C4/C5 - a rejected context reserves nothing and sends nothing."""
    budget = make_budget()
    transport = FakeTransport()
    prepared = PreparedRequest(status="CONTEXT_TOO_LARGE", messages=[])

    with pytest.raises(BaseException) as excinfo:
        rb.dispatch(prepared, budget, transport.send)

    exc = excinfo.value
    assert isinstance(exc, rb.ContextTooLarge), (
        f"C5 rejection must be the typed ContextTooLarge from the owner, got {type(exc)!r}"
    )
    assert transport.send_count == 0, "a rejected context must not send"
    snap = snapshot_of(budget)
    assert snap["charged_attempts"] == 0
    assert snap["active_reservations"] == 0
    assert snap["exhausted"] is False


def test_t_nfr01_boundary_context_too_large_with_last_slot_remaining():
    """T-NFR01-BOUNDARY: C5-first - rejection does not consume the last slot."""
    budget = make_budget()
    transport = FakeTransport()
    dispatch_ok(budget, transport)
    dispatch_ok(budget, transport)
    rejected = PreparedRequest(status="CONTEXT_TOO_LARGE")
    with pytest.raises(rb.ContextTooLarge):
        rb.dispatch(rejected, budget, transport.send)
    assert snapshot_of(budget)["charged_attempts"] == 2
    # The last slot is still available for a READY request.
    dispatch_ok(budget, transport)
    assert transport.send_count == LIMIT


# ---------------------------------------------------------------------------
# Cancellation semantics (OPEN-6)
# ---------------------------------------------------------------------------


def test_t_nfr01_failure_cancel_before_send_releases_headroom():
    """T-NFR01-FAILURE: OPEN-6/C4 - pre-send cancel releases a slot, zero sends."""
    budget = make_budget()
    transport = FakeTransport()
    ticket = budget.try_reserve()
    assert ticket is not None
    budget.cancel_before_send(ticket)
    assert transport.send_count == 0
    snap = snapshot_of(budget)
    assert snap["active_reservations"] == 0
    assert snap["charged_attempts"] == 0

    # Headroom released: three sends still fit, and the cancelled ticket does
    # not count toward the cap.
    for _ in range(3):
        dispatch_ok(budget, transport)
    assert transport.send_count == LIMIT
    assert snapshot_of(budget)["charged_attempts"] == LIMIT


def test_t_nfr01_failure_double_cancel_releases_at_most_once():
    """T-NFR01-FAILURE: OPEN-6 - a second cancel is an idempotent no-op."""
    budget = make_budget()
    ticket = budget.try_reserve()
    budget.cancel_before_send(ticket)
    budget.cancel_before_send(ticket)  # idempotent
    snap = snapshot_of(budget)
    assert snap["active_reservations"] == 0
    assert snap["charged_attempts"] == 0


def test_t_nfr01_failure_cancel_after_charge_raises_and_keeps_slot():
    """T-NFR01-FAILURE: OPEN-6 - cancelling a charged ticket raises, no refund."""
    budget = make_budget()
    transport = FakeTransport()
    ticket = budget.try_reserve()
    budget.charge_attempt(ticket)
    transport.send(PreparedRequest().messages)

    with pytest.raises(RuntimeError):
        budget.cancel_before_send(ticket)

    snap = snapshot_of(budget)
    assert snap["charged_attempts"] == 1, "cancel-after-charge must not refund the slot"
    assert snap["active_reservations"] == 0


# ---------------------------------------------------------------------------
# T-INV02-RACE - two contenders for the last slot, deterministic barrier
# ---------------------------------------------------------------------------


def test_t_inv02_race_two_contenders_last_slot_once():
    """T-INV02-RACE: INV-02/NFR-01/C4 - exactly one send and one refusal."""
    iterations = 20
    for iteration in range(iterations):
        budget = make_budget()
        transport = FakeTransport()
        # Spend LIMIT - 1 slots through real sends so the race is for the last one.
        for _ in range(LIMIT - 1):
            dispatch_ok(budget, transport)
        assert transport.send_count == LIMIT - 1

        barrier = threading.Barrier(2)
        granted: list[int] = []
        refused: list[int] = []
        errors: list[BaseException] = []

        def worker(index: int, budget=budget, transport=transport, barrier=barrier,
                   granted=granted, refused=refused, errors=errors):
            try:
                barrier.wait(timeout=10)
                ticket = budget.try_reserve()
                if ticket is None:
                    refused.append(index)
                    return
                budget.charge_attempt(ticket)
                transport.send(f"race-{index}")
                granted.append(index)
            except BaseException as exc:  # surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert not errors, f"iteration {iteration}: worker errors {errors!r}"
        assert not any(t.is_alive() for t in threads), f"iteration {iteration}: deadlock"
        assert len(granted) == 1, f"iteration {iteration}: exactly one winner, got {granted}"
        assert len(refused) == 1, f"iteration {iteration}: exactly one refusal, got {refused}"
        assert transport.send_count == LIMIT, (
            f"iteration {iteration}: the last-slot race must cause exactly one extra send"
        )
        snap = snapshot_of(budget)
        assert snap["charged_attempts"] == LIMIT
        assert snap["known_sends"] + snap["unknown_delivery"] == LIMIT
        assert snap["unknown_delivery"] == 1  # primitives bypass dispatch()'s delivery confirmation
        assert snap["known_sends"] == LIMIT - 1
        assert snap["exhausted"] is True


def test_t_inv02_race_dispatch_threads_from_same_budget():
    """T-INV02-RACE: INV-02 - concurrent dispatch() calls never exceed limit."""
    budget = make_budget()
    transport = FakeTransport()
    barrier = threading.Barrier(8)
    ok: list[int] = []
    refused: list[int] = []
    errors: list[BaseException] = []

    def worker(index: int, budget=budget, transport=transport, barrier=barrier,
               ok=ok, refused=refused, errors=errors):
        try:
            barrier.wait(timeout=10)
            try:
                dispatch_ok(budget, transport)
                ok.append(index)
            except rb.BudgetExhausted:
                refused.append(index)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, f"unexpected worker errors: {errors!r}"
    assert transport.send_count == LIMIT, "transport must never exceed the limit"
    assert len(ok) == LIMIT and len(refused) == 5


def test_t_inv02_race_dispatch_two_contenders_last_slot_once():
    """T-INV02-RACE: INV-02/NFR-01/Contract C4 v1.0 (interface-v1.0) - dispatch-level.

    Coverage addition (D-NFR01-09), not a defect fix: the dispatch boundary is
    already correct, so this test is expected GREEN on the approved baseline.
    Its discrimination evidence is a targeted mutation that removes the
    delivery-confirmation step inside dispatch() (the known-vs-unknown
    update); with that step removed this test MUST fail, and it passes again
    once the step is restored.

    Two contenders call dispatch() for the last slot of a limit-3 run behind
    one barrier: exactly one send, exactly one typed refusal, and - because
    every dispatched attempt is confirmed - zero unknown_delivery.
    """
    iterations = 20
    for iteration in range(iterations):
        budget = make_budget()
        transport = FakeTransport()
        for _ in range(LIMIT - 1):
            dispatch_ok(budget, transport)
        assert transport.send_count == LIMIT - 1

        barrier = threading.Barrier(2)
        granted: list[int] = []
        refused: list[int] = []
        errors: list[BaseException] = []

        def worker(index: int, budget=budget, transport=transport, barrier=barrier,
                   granted=granted, refused=refused, errors=errors):
            try:
                barrier.wait(timeout=10)
                try:
                    dispatch_ok(budget, transport)
                    granted.append(index)
                except rb.BudgetExhausted:
                    refused.append(index)
            except BaseException as exc:  # surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert not errors, f"iteration {iteration}: worker errors {errors!r}"
        assert not any(t.is_alive() for t in threads), f"iteration {iteration}: deadlock"
        assert len(granted) == 1 and len(refused) == 1, (
            f"iteration {iteration}: expected one grant and one refusal, "
            f"got granted={granted} refused={refused}"
        )
        assert transport.send_count == LIMIT, (
            f"iteration {iteration}: the last-slot race must cause exactly one extra send"
        )
        snap = snapshot_of(budget)
        assert snap["charged_attempts"] == LIMIT
        assert snap["known_sends"] == LIMIT, (
            f"iteration {iteration}: every dispatched attempt must be delivery-confirmed; "
            f"got known_sends={snap['known_sends']}"
        )
        assert snap["unknown_delivery"] == 0, (
            f"iteration {iteration}: dispatch() must confirm delivery, "
            f"got unknown_delivery={snap['unknown_delivery']}"
        )
        assert snap["active_reservations"] == 0
        assert snap["exhausted"] is True
