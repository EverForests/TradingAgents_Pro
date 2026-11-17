"""FR-01 / INV-01 R8-B — C0/C1 v1.0 alignment of the publication gate.

Baseline: ``712617e25a380197e38d6ee5cc4dcc7ab393cf61``; contracts C0/C1 v1.0.
Case IDs: T-FR01-RATING, T-FR01-MISSING, T-FR01-REFERENCE, T-FR01-SINKS,
T-INV01-BYPASS. Approved plan: R8-B (§1–§3) plus the supplementary note (§2.3).

Skipped is not passed
---------------------

The v1 owner symbols (``evaluate_publication``, ``PublicationRequiredError``) do
not exist at this baseline. Every case below goes through ``_gate()`` /
``_owner()``, which calls ``pytest.skip`` with a reason naming the missing
symbol. A baseline run therefore reports them as **skipped**. A skip is **not**
B acceptance evidence: each case is a post-implementation obligation that must
execute and pass once the implementation lands. Skipping is never counted as a
pass and never stands in for a result.

What this file verifies (from the approved plan and C0/C1 v1.0):

- Gate order and each terminal state (§2 table): BUDGET_EXHAUSTED,
  CONTEXT_TOO_LARGE, RUN_NOT_COMPLETE, INVALID_RATING, INSUFFICIENT_EVIDENCE,
  then APPROVED. The first matching row wins.
- ``evaluate_publication(candidate, argument_index, evidence_index, run)`` is the
  one entry; ``PublicationResult`` carries identity, status, ``reason_codes``,
  ``rating`` (None unless APPROVED), ``argument_ids`` and ``evidence_ids``.
- Only ``argument_index`` / ``evidence_index`` resolve references (§3): an
  ``accepted_arguments`` view is never a release authority.
- All four official sinks (Python return, CLI, saved report, decision memory)
  consume the same ``publication_result``; a BLOCKED run reaches none of them.
- A foreign run's evidence never resolves (§2 row 5, §2.1 of the note).

How the sink cases run
----------------------

The four sinks are exercised by running the **real** pipeline, not by calling
the gate or the publish step in place of it:

* ``propagate()`` on a production ``TradingAgentsGraph`` runs end to end. Only
  the two model tiers are scripted (:class:`_ScriptedModel`, a deterministic
  fake that answers from the prompt it is given and returns real ``pydantic``
  schema instances for the structured calls); the analyst, the graph's
  ``Index Evidence`` step, the debate, the researchers' evidence validation,
  the gate and every sink are production code, ``checkpoint_enabled`` is off,
  and no vendor is reached.
* The APPROVED runs cite the evidence id the Bull is actually shown in the run's
  evidence menu. The BLOCKED runs use the *same* graph and scripts and differ in
  one thing only: the Portfolio Manager's candidate cites no argument. So a
  difference between the two must come from the gate, not from the fixture.
* The CLI case drives the real ``cli.run`` entry over that same graph; the only
  replacement is the live view and the console, and the graph the CLI built is
  read back to confirm its own gate call decided as expected.

Fixture shape (C0/C1 v1.0)
--------------------------

* Every shared evidence and argument record carries ``contract_version``,
  ``run_id``, ``ticker`` and ``as_of_date`` beside its own contract fields, and
  both indexes are **mappings keyed by ID** (``evidence_id`` / ``argument_id``),
  as v1.0 requires — not lists that the gate has to search.
* A record whose ``content_ref`` is exercised is backed by **fixed material that
  can be read back**: the fixture writes ``call-1.md`` under the retention root
  and the tests read it through :func:`_read_content`.
* The cross-run counterexamples change **only** the current run identity (the
  ``RunContext`` handed to the gate, or the ``run_id`` of the state reaching a
  sink). Every fixture record is otherwise the same run A material, so a
  same-run positive control with the identical fixtures must APPROVE. That
  contrast is what isolates identity from content.

No v1 implementation exists yet, so the gate-contract and sink cases here report
as skipped at this baseline; each one must execute after implementation.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableLambda

import tradingagents.graph.trading_graph  # noqa: F401 — the project's own entry order
from tradingagents.graph import publication_gate as gate

# --- C0/C1 v1.0 vocabulary ----------------------------------------------------

CONTRACT_VERSION = "1.0"
APPROVED = "APPROVED"
BLOCKED = "BLOCKED"

BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
CONTEXT_TOO_LARGE = "CONTEXT_TOO_LARGE"
RUN_NOT_COMPLETE = "RUN_NOT_COMPLETE"
INVALID_RATING = "INVALID_RATING"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
COMPLETED = "COMPLETED"

TICKER = "AAPL"
AS_OF_DATE = "2026-11-10"
RUN_A = "run-a-0001"
RUN_B = "run-b-0002"

# An analyst report's prose. It is *not* admissible evidence: a record that names
# no retained material cannot back a release, so this text never appears in a
# passing fixture's evidence index. It stays for the cases that assert a
# report-only record is refused.
REPORT_TEXT = "AAPL closed at 348.245 USD."

# The retention root R8-B §4.3 fixes: {results_dir}/{ticker}/{trade_date}/evidence/{run_id}/
EVIDENCE_FILE = "call-1.md"
SNAPSHOT_MATERIAL = (
    "## Verified market data snapshot for AAPL\n\n"
    "### Recent verified closes (last 2 rows)\n\n"
    "| Date | Close |\n"
    "|---|---:|\n"
    "| 2026-11-09 | 351.60 |\n"
    "| 2026-11-10 | 348.245 |\n"
)
WINDOW_START = "2026-11-03"
WINDOW_END = AS_OF_DATE

BUY = "Buy"

# Any official surface carrying this marker has released the candidate body
# (INV-01). Deliberately not a rating word.
MARKER = "INV01-UNPUBLISHED-CANDIDATE-BODY-7f3c"
CANDIDATE_BODY = (
    f"**Rating**: {BUY}\n\n"
    "**Executive Summary**: add on the breakout.\n\n"
    f"**Investment Thesis**: {MARKER} price holds above the Bollinger upper band."
)


def _gate():
    """``evaluate_publication``, or a skip naming it as the missing symbol.

    R8-B implements ``evaluate_publication``; after this revision the case must
    execute. The guard stays so an environment that somehow lacks the symbol
    reports a named skip rather than a misleading pass or an AttributeError.
    """
    evaluate = getattr(gate, "evaluate_publication", None)
    if evaluate is None:
        pytest.skip(
            "publication_gate.evaluate_publication is absent in this environment, so the "
            "C0/C1 v1.0 behaviour below cannot be exercised; this case is NOT a pass"
        )
    return evaluate


def _run(run_id: str, execution_status: str = COMPLETED) -> dict:
    """A complete RunContext as C0/C1 v1.0 and R8-B §1 specify it."""
    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "ticker": TICKER,
        "as_of_date": AS_OF_DATE,
        "execution_status": execution_status,
        "request_limit": 40,
    }


# --- fixed, readable material ------------------------------------------------


def _retention_dir(results_dir: Path) -> Path:
    """The §4.3 retention root for run A."""
    return Path(results_dir) / TICKER / AS_OF_DATE / "evidence" / RUN_A


def _write_material(results_dir: Path) -> Path:
    """Write the fixed snapshot material the ``content_ref`` points at."""
    root = _retention_dir(results_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / EVIDENCE_FILE
    path.write_text(SNAPSHOT_MATERIAL, encoding="utf-8")
    return path


def _read_content(results_dir: Path, content_ref: str) -> str:
    """Resolve ``evidence://{run_id}/{name}`` to the retained material's text.

    The path is rebuilt from the §4.3 components under ``results_dir``, so a
    reference naming another run resolves only if that run's material exists.
    """
    prefix = "evidence://"
    assert content_ref.startswith(prefix), f"not an evidence reference: {content_ref!r}"
    run_id, _, name = content_ref[len(prefix):].partition("/")
    path = Path(results_dir) / TICKER / AS_OF_DATE / "evidence" / run_id / name
    assert path.is_file(), f"content_ref does not resolve: {content_ref!r}"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def results(tmp_path) -> Path:
    """A fresh results root holding run A's fixed, readable material."""
    root = tmp_path / "results"
    _write_material(root)
    return root


# --- C0/C1 v1.0 shared records ------------------------------------------------


def _identity(run_id: str) -> dict:
    """The identity fields every shared evidence and argument record carries."""
    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "ticker": TICKER,
        "as_of_date": AS_OF_DATE,
    }


def _evidence_id(run_id: str) -> str:
    return f"ev:{run_id}:market"


def _snapshot_record(run_id: str, evidence_id: str | None = None,
                     content_ref: str | None = None) -> dict:
    """One complete C1 v1.0 ``EvidenceRecord`` for ``run_id``.

    Every required shared field is present — ``source_kind``, ``vendor``,
    ``source_ref``, ``content_ref`` and the request window — because a record
    missing any of them is an invalid record, not evidence. Reused wherever a
    case needs a genuinely admissable snapshot so the only property under test is
    the one the case names.
    """
    evidence_id = evidence_id or _evidence_id(run_id)
    return {
        **_identity(run_id),
        "evidence_id": evidence_id,
        "source_kind": "market_snapshot",
        "vendor": "yahoo",
        "source_ref": (
            "tool:get_verified_market_snapshot?tool_call_id=call-1"
            f"&curr_date={AS_OF_DATE}&look_back_days=7"
        ),
        "content_ref": content_ref or f"evidence://{run_id}/{EVIDENCE_FILE}",
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
    }


def _evidence_index(run_id: str) -> dict:
    """The evidence index as a mapping keyed by ``evidence_id`` (C1 v1.0).

    Each record holds ``ticker`` / ``as_of_date``, source kind and vendor,
    the request window, the source locator and the retained content reference
    (C1: "An EvidenceRecord contains run_id, evidence_id, source kind/vendor,
    request ticker/window, source locator ... and source content/reference").
    """
    record = _snapshot_record(run_id)
    return {record["evidence_id"]: record}


def _argument_id(run_id: str) -> str:
    return f"arg:bull:{run_id}:1"


def _argument_index(run_id: str) -> dict:
    """The argument index as a mapping keyed by ``argument_id`` (C1 v1.0)."""
    record = {
        **_identity(run_id),
        "argument_id": _argument_id(run_id),
        "claim": "Price holds above the Bollinger upper band.",
        "evidence_ids": [_evidence_id(run_id)],
    }
    return {record["argument_id"]: record}


def _candidate(rating=BUY, argument_ids=()) -> dict:
    """The Portfolio Manager's candidate; the rating string is untrusted (C1)."""
    return {
        "rating": rating,
        "argument_ids": list(argument_ids),
        "body": CANDIDATE_BODY,
    }


def _evaluate(run_id=RUN_A, *, rating=BUY, argument_ids=None, status=COMPLETED,
              evidence_index=None, argument_index=None, run=None, results_dir=None):
    """Call the real ``evaluate_publication`` with v1.0 fixtures.

    ``results_dir`` is the root the gate re-reads each record's retained material
    from; the test passes the same temporary root the material was written under,
    because a reference the gate cannot resolve is not evidence. The gate reads
    retained material only — a record that names no material is never evidence —
    so no report text is handed to it.
    """
    evaluate = _gate()
    if argument_ids is None:
        argument_ids = (_argument_id(run_id),)
    return evaluate(
        _candidate(rating, argument_ids),
        argument_index if argument_index is not None else _argument_index(run_id),
        evidence_index if evidence_index is not None else _evidence_index(run_id),
        run if run is not None else _run(run_id, status),
        results_dir=results_dir,
    )


@pytest.fixture
def gate_evaluate(results):
    """``_evaluate`` bound to the fixture's results root."""
    def _call(*a, **k):
        k.setdefault("results_dir", results)
        return _evaluate(*a, **k)

    return _call


# --- §2 rows 1–3: execution state --------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("execution_status", "expected_code"),
    [
        (BUDGET_EXHAUSTED, BUDGET_EXHAUSTED),
        (CONTEXT_TOO_LARGE, CONTEXT_TOO_LARGE),
        # A missing course_run and any other non-COMPLETED state are RUN_NOT_COMPLETE.
        ("FAILED", RUN_NOT_COMPLETE),
        ("RUNNING", RUN_NOT_COMPLETE),
        (None, RUN_NOT_COMPLETE),
    ],
    ids=["budget-exhausted", "context-too-large", "failed", "still-running", "missing-course-run"],
)
def test_non_completed_execution_blocks_with_its_own_code(results, execution_status, expected_code):
    """Rows 1–3: a terminal run keeps its own reason; no candidate may publish."""
    evaluate = _gate()
    run = None if execution_status is None else _run(RUN_A, execution_status)

    result = evaluate(
        _candidate(BUY, (_argument_id(RUN_A),)),
        _argument_index(RUN_A),
        _evidence_index(RUN_A),
        run,
        results_dir=results,
    )
    assert result.publication_status == BLOCKED
    assert expected_code in result.reason_codes
    assert result.rating is None
    assert CANDIDATE_BODY not in repr(result)


# --- §2 rows 4–5: rating and references ---------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "rating",
    ["Strong Buy", "REVIEW", "buy", "", "Buy (small size)", None],
    ids=["free-text", "review", "lowercase", "empty", "trailing-text", "null"],
)
def test_rating_outside_the_five_tiers_is_invalid_rating(gate_evaluate, rating):
    """Row 4: only the five tiers are publishable; REVIEW and free text are not."""
    result = gate_evaluate(rating=rating)
    assert result.publication_status == BLOCKED
    assert result.reason_codes == (INVALID_RATING,) or INVALID_RATING in result.reason_codes
    assert result.rating is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "argument_ids",
    [(), ("arg:does-not-exist",), (_argument_id(RUN_B),)],
    ids=["missing", "unknown", "foreign-run-id"],
)
def test_unresolvable_reference_is_insufficient_evidence(gate_evaluate, argument_ids):
    """Row 5: missing, unknown or another run's argument cannot publish.

    The third case changes only the ID's run segment; run A's fixtures stay as
    they are, so the same-run positive control in
    ``test_accepted_arguments_view_is_not_a_release_authority`` covers content.
    """
    result = gate_evaluate(argument_ids=argument_ids)
    assert result.publication_status == BLOCKED
    assert INSUFFICIENT_EVIDENCE in result.reason_codes
    assert result.rating is None


@pytest.mark.unit
def test_accepted_arguments_view_is_not_a_release_authority(results):
    """§3: an ``accepted_arguments`` view alone never resolves a reference.

    The same argument passes when it is in ``argument_index`` and fails when the
    only copy is the compatibility view handed to the gate as extra state.
    """
    evaluate = _gate()
    argument_id = _argument_id(RUN_A)
    candidate = _candidate(BUY, (argument_id,))
    evidence_index = _evidence_index(RUN_A)

    authoritative = evaluate(
        candidate, _argument_index(RUN_A), evidence_index, _run(RUN_A),
        results_dir=results,
    )
    assert authoritative.publication_status == APPROVED, authoritative.reason_codes

    view_only = {"accepted_arguments": list(_argument_index(RUN_A).values())}
    without_index = evaluate(
        candidate, view_only, evidence_index, _run(RUN_A),
        results_dir=results,
    )
    assert without_index.publication_status == BLOCKED
    assert INSUFFICIENT_EVIDENCE in without_index.reason_codes


@pytest.mark.unit
def test_foreign_evidence_index_never_resolves(results):
    """A complete run A index on run B: identity comes from course_run (§1).

    Only the RunContext changes — the candidate, the argument index and the
    evidence index are byte-identical to the same-run control that APPROVES in
    ``test_valid_run_approves_with_identity_and_resolved_references``.
    """
    result = _evaluate(
        run=_run(RUN_B),
        argument_ids=(_argument_id(RUN_A),),
        evidence_index=_evidence_index(RUN_A),
        argument_index=_argument_index(RUN_A),
        results_dir=results,
    )
    assert result.publication_status == BLOCKED
    assert INSUFFICIENT_EVIDENCE in result.reason_codes
    assert result.rating is None


# --- §2 row 5: the reported false approval, reproduced ------------------------


@pytest.mark.unit
def test_argument_without_identity_is_refused_even_in_a_named_run(results):
    """C1: an argument record must state its own full identity, not inherit the run.

    The run has a ``run_id`` and the evidence record is complete and resolvable,
    so a record that merely *looks* accepted is the only thing standing between
    the candidate and approval. An argument that names no identity at all is not
    owned by this run and must not resolve; the identical argument with the full
    identity approves, so the refusal is about identity, not content.
    """
    evaluate = _gate()
    identity_less = {
        _argument_id(RUN_A): {
            # No contract_version / run_id / ticker / as_of_date at all.
            "argument_id": _argument_id(RUN_A),
            "speaker": "Bull Analyst",
            "evidence_ids": [_evidence_id(RUN_A)],
        },
    }
    blocked = evaluate(
        _candidate(BUY, (_argument_id(RUN_A),)),
        identity_less,
        _evidence_index(RUN_A),
        _run(RUN_A),
        results_dir=results,
    )
    assert blocked.publication_status == BLOCKED, (
        "an argument with no identity was accepted because the run had a run id"
    )
    assert INSUFFICIENT_EVIDENCE in blocked.reason_codes
    assert blocked.rating is None

    # Same argument, full v1 identity: approved.
    approved = evaluate(
        _candidate(BUY, (_argument_id(RUN_A),)),
        _argument_index(RUN_A),
        _evidence_index(RUN_A),
        _run(RUN_A),
        results_dir=results,
    )
    assert approved.publication_status == APPROVED, approved.reason_codes


@pytest.mark.unit
def test_partial_argument_identity_is_refused(results):
    """C1: a partial identity (only ``run_id``) is not a full identity."""
    evaluate = _gate()
    partial = {
        _argument_id(RUN_A): {
            "run_id": RUN_A,
            "argument_id": _argument_id(RUN_A),
            "speaker": "Bull Analyst",
            "evidence_ids": [_evidence_id(RUN_A)],
        },
    }
    result = evaluate(
        _candidate(BUY, (_argument_id(RUN_A),)),
        partial,
        _evidence_index(RUN_A),
        _run(RUN_A),
        results_dir=results,
    )
    assert result.publication_status == BLOCKED
    assert INSUFFICIENT_EVIDENCE in result.reason_codes


@pytest.mark.unit
def test_evidence_wrapper_mapping_is_read_not_treated_as_records(results):
    """C1: the v1 ``{"run_id", "evidence": {id: record}}`` wrapper is a mapping index.

    This is the shape ``Index Evidence`` writes. Its metadata key must never be
    read as a record, and the wrapped mapping must resolve, so a run that cites
    its own retained snapshot approves.
    """
    evaluate = _gate()
    wrapped = {"run_id": RUN_A, "evidence": dict(_evidence_index(RUN_A))}
    result = evaluate(
        _candidate(BUY, (_argument_id(RUN_A),)),
        _argument_index(RUN_A),
        wrapped,
        _run(RUN_A),
        results_dir=results,
    )
    assert result.publication_status == APPROVED, result.reason_codes
    assert _evidence_id(RUN_A) in result.evidence_ids


@pytest.mark.unit
def test_legacy_records_with_unknown_references_do_not_publish(results):
    """The reported defect: old records, an unknown argument and unknown evidence.

    Codex measured that a run whose report record has no source material and
    whose candidate cites both an unknown argument and an unknown evidence id
    still returned APPROVED. Each part is now fatal on its own; together they
    must not publish, and the result must carry no rating.

    The control at the end differs by exactly one property — the argument is
    accepted and its evidence resolves — so the block comes from the gate, not
    from the fixtures.
    """
    evaluate = _gate()
    argument_id = _argument_id(RUN_A)

    # A legacy report record: no identity, no material reference, no source kind.
    legacy_evidence = {
        "run_id": RUN_A,
        "evidence": [{"id": "legacy-report", "source": "market_report", "excerpt": "old"}],
    }
    legacy_arguments = {
        "run_id": RUN_A,
        "arguments": [{
            "id": "legacy-argument",
            "speaker": "Bull Analyst",
            "text": "old argument",
            "evidence_ids": ["missing-evidence"],
        }],
    }

    # (a) old report record + an unknown argument cited by the candidate.
    blocked = evaluate(
        _candidate(BUY, (argument_id,)),
        legacy_arguments,
        legacy_evidence,
        _run(RUN_A),
        results_dir=results,
    )
    assert blocked.publication_status == BLOCKED, (
        "a legacy record set with no identity or material must not publish"
    )
    assert INSUFFICIENT_EVIDENCE in blocked.reason_codes
    assert blocked.rating is None

    # (b) the same, with an unknown evidence id inside the cited argument.
    blocked = evaluate(
        _candidate(BUY, ("legacy-argument",)),
        legacy_arguments,
        legacy_evidence,
        _run(RUN_A),
        results_dir=results,
    )
    assert blocked.publication_status == BLOCKED
    assert INSUFFICIENT_EVIDENCE in blocked.reason_codes

    # Control: the complete v1 records with resolvable material still publish.
    approved = evaluate(
        _candidate(BUY, (argument_id,)),
        _argument_index(RUN_A),
        _evidence_index(RUN_A),
        _run(RUN_A),
        results_dir=results,
    )
    assert approved.publication_status == APPROVED, approved.reason_codes


# --- R8-B v1.0 boundaries: any invalid reference rejects the whole candidate --
#
# C1 v1.0: "missing, unknown, cross-run or unaccepted required references use
# INSUFFICIENT_EVIDENCE". A candidate is a single recommendation: one unresolvable
# reference makes it unverifiable, so it must block as a whole. Every case below
# is paired with a same-material control, so the refusal is attributable to the
# one property under test and not to the fixtures.


def _unknown_argument_id() -> str:
    """An argument id that no index in these fixtures contains."""
    return f"arg:bull:{RUN_A}:unknown"


@pytest.mark.unit
def test_one_unknown_argument_rejects_the_whole_candidate(results):
    """Mixed reference 1: a valid argument plus an unknown one blocks the candidate.

    The valid argument resolves completely, so the candidate would approve if the
    gate silently skipped what it could not verify. It must instead refuse the
    whole recommendation: there is no partial approval.
    """
    evaluate = _gate()
    good = _argument_id(RUN_A)
    unknown = _unknown_argument_id()

    mixed = evaluate(
        _candidate(BUY, (good, unknown)),
        _argument_index(RUN_A),
        _evidence_index(RUN_A),
        _run(RUN_A),
        results_dir=results,
    )
    assert mixed.publication_status == BLOCKED, (
        "a candidate citing an unknown argument alongside a valid one published"
    )
    assert INSUFFICIENT_EVIDENCE in mixed.reason_codes
    assert mixed.rating is None
    assert MARKER not in repr(mixed)

    # Control: the same candidate without the unknown reference approves.
    control = evaluate(
        _candidate(BUY, (good,)),
        _argument_index(RUN_A),
        _evidence_index(RUN_A),
        _run(RUN_A),
        results_dir=results,
    )
    assert control.publication_status == APPROVED, control.reason_codes


@pytest.mark.unit
def test_argument_citing_a_mix_of_known_and_unknown_evidence_is_refused(results):
    """Mixed reference 2: one argument citing valid *and* unknown evidence fails.

    Both layers must refuse it: ``validate_argument`` never accepts the argument
    into the index, and even a record that reached the index anyway must not back
    a release.
    """
    evaluate = _gate()
    argument_id = _argument_id(RUN_A)
    mixed_argument = {
        argument_id: {
            **_identity(RUN_A),
            "argument_id": argument_id,
            "claim": "Price holds above the upper band on unverifiable volume.",
            # The first id resolves; the second exists nowhere.
            "evidence_ids": [_evidence_id(RUN_A), f"ev:{RUN_A}:market_snapshot:missing"],
        },
    }

    # Layer 1: the argument is never accepted.
    validate = getattr(gate, "validate_argument", None)
    assert validate is not None, (
        "publication_gate.validate_argument is missing; C1 v1.0 requires it"
    )
    assert validate(mixed_argument[argument_id], _evidence_index(RUN_A), _run(RUN_A),
                    results_dir=results) is None, (
        "an argument citing an unknown evidence id was accepted"
    )

    # Layer 2: even if such a record reached the index, the gate refuses the run.
    blocked = evaluate(
        _candidate(BUY, (argument_id,)),
        mixed_argument,
        _evidence_index(RUN_A),
        _run(RUN_A),
        results_dir=results,
    )
    assert blocked.publication_status == BLOCKED, (
        "an argument citing an unknown evidence id backed a release"
    )
    assert INSUFFICIENT_EVIDENCE in blocked.reason_codes
    assert blocked.rating is None

    # Control: the same argument with only the resolvable id approves.
    control = evaluate(
        _candidate(BUY, (argument_id,)),
        _argument_index(RUN_A),
        _evidence_index(RUN_A),
        _run(RUN_A),
        results_dir=results,
    )
    assert control.publication_status == APPROVED, control.reason_codes


_EVIDENCE_REQUIRED_FIELDS = (
    "evidence_id", "source_kind", "vendor", "source_ref",
    "content_ref", "window_start", "window_end",
)


@pytest.mark.unit
@pytest.mark.parametrize("field", _EVIDENCE_REQUIRED_FIELDS)
def test_evidence_missing_a_required_field_is_not_evidence(results, field):
    """C1 v1.0: "a missing required field is an invalid record", not evidence."""
    evaluate = _gate()
    record = dict(_evidence_index(RUN_A)[_evidence_id(RUN_A)])
    record.pop(field)

    result = evaluate(
        _candidate(BUY, (_argument_id(RUN_A),)),
        _argument_index(RUN_A),
        {_evidence_id(RUN_A): record},
        _run(RUN_A),
        results_dir=results,
    )
    assert result.publication_status == BLOCKED, (
        f"an evidence record with no {field!r} backed a release"
    )
    assert INSUFFICIENT_EVIDENCE in result.reason_codes
    assert result.rating is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "value"),
    [("claim", ""), ("claim", "   "), ("evidence_ids", []), ("evidence_ids", None)],
    ids=["empty-claim", "blank-claim", "no-evidence-ids", "null-evidence-ids"],
)
def test_argument_missing_a_required_field_is_refused(results, field, value):
    """C1 v1.0: an AcceptedArgument needs a nonempty claim and a nonempty list."""
    evaluate = _gate()
    argument_id = _argument_id(RUN_A)
    record = dict(_argument_index(RUN_A)[argument_id])
    record[field] = value

    # The argument is not accepted at the validation layer...
    validate = getattr(gate, "validate_argument", None)
    assert validate is not None, (
        "publication_gate.validate_argument is missing; C1 v1.0 requires it"
    )
    assert validate(record, _evidence_index(RUN_A), _run(RUN_A), results_dir=results) is None, (
        f"an argument with {field}={value!r} was accepted"
    )

    # ...and it cannot back a release if it reached the index anyway.
    blocked = evaluate(
        _candidate(BUY, (argument_id,)),
        {argument_id: record},
        _evidence_index(RUN_A),
        _run(RUN_A),
        results_dir=results,
    )
    assert blocked.publication_status == BLOCKED
    assert INSUFFICIENT_EVIDENCE in blocked.reason_codes
    assert blocked.rating is None


@pytest.mark.unit
def test_blank_retained_material_is_not_evidence(tmp_path):
    """A reference to a file that holds no content is not substantive evidence.

    Assigning an ID does not make empty content valid: the retained file exists,
    but it says nothing, so it cannot prove a market claim. The control rewrites
    the same file with real material and the identical records approve.
    """
    evaluate = _gate()
    results_dir = Path(tmp_path / "results")
    material = _write_material(results_dir)

    for blank in ("", "   \n\t\n", "\n\n"):
        material.write_text(blank, encoding="utf-8")
        blocked = evaluate(
            _candidate(BUY, (_argument_id(RUN_A),)),
            _argument_index(RUN_A),
            _evidence_index(RUN_A),
            _run(RUN_A),
            results_dir=results_dir,
        )
        assert blocked.publication_status == BLOCKED, (
            f"whitespace-only retained material ({blank!r}) backed a release"
        )
        assert INSUFFICIENT_EVIDENCE in blocked.reason_codes
        assert blocked.rating is None

    # Control: the same reference to real material approves.
    material.write_text(SNAPSHOT_MATERIAL, encoding="utf-8")
    approved = evaluate(
        _candidate(BUY, (_argument_id(RUN_A),)),
        _argument_index(RUN_A),
        _evidence_index(RUN_A),
        _run(RUN_A),
        results_dir=results_dir,
    )
    assert approved.publication_status == APPROVED, approved.reason_codes


@pytest.mark.unit
def test_validate_argument_returns_the_accepted_record_with_full_identity(results):
    """C1 v1.0: ``validate_argument`` checks current-run references before acceptance.

    It returns the accepted record — carrying the run's full identity plus the
    claim and the resolved evidence ids — or a refusal. A model flag is not
    acceptance, and a foreign run's or unknown reference is not resolvable here.
    """
    validate = getattr(gate, "validate_argument", None)
    assert validate is not None, (
        "publication_gate.validate_argument is missing; C1 v1.0 requires it"
    )
    argument = _argument_index(RUN_A)[_argument_id(RUN_A)]

    accepted = validate(argument, _evidence_index(RUN_A), _run(RUN_A), results_dir=results)
    assert accepted is not None, "a valid argument was refused"
    accepted = accepted if isinstance(accepted, dict) else getattr(accepted, "__dict__", {})
    assert accepted.get("argument_id") == _argument_id(RUN_A)
    for key in ("run_id", "ticker", "as_of_date"):
        assert accepted.get(key) == _run(RUN_A)[key], (
            f"the accepted record did not keep the run's {key!r}"
        )
    assert accepted.get("evidence_ids") == [_evidence_id(RUN_A)]
    assert (accepted.get("claim") or accepted.get("text")), "the claim was dropped"

    # An unknown evidence id, a foreign run's evidence and an empty claim refuse.
    unknown = dict(argument, evidence_ids=[f"ev:{RUN_A}:market_snapshot:missing"])
    foreign = dict(argument, evidence_ids=[_evidence_id(RUN_B)])
    blank = dict(argument, claim="  ")
    for label, candidate in (
        ("unknown evidence", unknown), ("foreign evidence", foreign),
        ("blank claim", blank),
    ):
        assert validate(candidate, _evidence_index(RUN_A), _run(RUN_A),
                        results_dir=results) is None, (
            f"validate_argument accepted an argument with {label}"
        )


@pytest.mark.unit
def test_failed_execution_does_not_publish(monkeypatch, tmp_path):
    """C0: FAILED is a terminal execution state, not a finished run.

    ``complete_run`` must never promote FAILED to COMPLETED, and a FAILED run's
    publication result is BLOCKED / RUN_NOT_COMPLETE — while the budget and
    context failures keep their own reason codes.
    """
    _owner()
    graph = _make_graph(monkeypatch, tmp_path)
    state = _run_state()
    state["course_run"] = {**_run(RUN_A), "execution_status": "FAILED"}
    state["execution_status"] = "FAILED"

    # complete_run must not overwrite a terminal failure.
    graph.complete_run(state)
    assert state["course_run"]["execution_status"] == "FAILED", (
        "complete_run() promoted a FAILED run to COMPLETED"
    )
    assert state["execution_status"] == "FAILED"

    state["candidate_rating"] = BUY
    state["candidate_decision"] = CANDIDATE_TEXT
    state["candidate_argument_ids"] = [_argument_id(RUN_A)]
    _publish(graph, state)

    assert state["publication_status"] == BLOCKED
    assert state["publication_reason"] == RUN_NOT_COMPLETE
    assert state.get("final_rating") in (None, "")
    assert MARKER not in repr(state.get("final_trade_decision"))

    # The budget and context failures keep their own dedicated codes.
    for status, code in ((BUDGET_EXHAUSTED, BUDGET_EXHAUSTED),
                         (CONTEXT_TOO_LARGE, CONTEXT_TOO_LARGE)):
        failed = _run_state()
        failed["course_run"] = {**_run(RUN_A), "execution_status": status}
        failed["execution_status"] = status
        graph.complete_run(failed)
        assert failed["course_run"]["execution_status"] == status, (
            f"complete_run() overwrote the terminal state {status}"
        )
        failed["candidate_rating"] = BUY
        failed["candidate_decision"] = CANDIDATE_TEXT
        failed["candidate_argument_ids"] = [_argument_id(RUN_A)]
        _publish(graph, failed)
        assert failed["publication_status"] == BLOCKED
        assert failed["publication_reason"] == code, (
            f"{status} lost its own reason code: {failed.get('publication_reason')!r}"
        )
        assert failed.get("final_rating") in (None, "")


@pytest.mark.unit
def test_shared_run_entry_creates_one_complete_run_context(monkeypatch, tmp_path):
    """C0/C1: the shared run entry writes the one complete ``RunContext``.

    Collection and the Index Evidence step reuse it rather than minting their own,
    so a resumed run keeps the identity its retained material was stamped with.
    """
    _owner()
    graph = _make_graph(monkeypatch, tmp_path)
    state = graph.create_run_state(TICKER, AS_OF_DATE, "stock")

    course_run = state.get("course_run")
    assert isinstance(course_run, dict), (
        "the shared run entry must write a complete RunContext, not None"
    )
    assert course_run.get("contract_version") == CONTRACT_VERSION
    assert course_run.get("run_id"), "the RunContext must carry the minted run id"
    assert course_run.get("ticker") == TICKER
    assert course_run.get("as_of_date") == AS_OF_DATE
    assert course_run.get("execution_status") == "RUNNING", (
        "a run that has not finished yet must start RUNNING"
    )
    limit = course_run.get("request_limit")
    assert isinstance(limit, int) and not isinstance(limit, bool) and limit > 0

    # The run id on the state is the same identity, so a resumed run reuses it.
    assert state.get("run_id") == course_run["run_id"]


@pytest.mark.unit
def test_evidence_with_expired_material_does_not_publish(tmp_path):
    """R8-B §4.3: a reference whose retained material is gone is not evidence.

    The positive control writes the material and approves; the same records are
    then evaluated after the material is removed, and the run must block.
    """
    evaluate = _gate()
    root = tmp_path / "results"
    material = _write_material(root)

    approved = evaluate(
        _candidate(BUY, (_argument_id(RUN_A),)),
        _argument_index(RUN_A),
        _evidence_index(RUN_A),
        _run(RUN_A),
        results_dir=root,
    )
    assert approved.publication_status == APPROVED, approved.reason_codes

    material.unlink()
    expired = evaluate(
        _candidate(BUY, (_argument_id(RUN_A),)),
        _argument_index(RUN_A),
        _evidence_index(RUN_A),
        _run(RUN_A),
        results_dir=root,
    )
    assert expired.publication_status == BLOCKED, (
        "evidence whose retained material expired must not publish"
    )
    assert INSUFFICIENT_EVIDENCE in expired.reason_codes
    assert expired.rating is None


@pytest.mark.unit
def test_identity_is_checked_on_the_record_not_the_id_spelling(results):
    """Ownership is the record's full identity: no ID prefix or run segment is needed.

    The same record approving under an id that carries neither ``ev:`` nor the run
    id shows the gate does not rely on spelling, while the same id with a foreign
    ``run_id`` inside the record is refused.
    """
    evaluate = _gate()
    plain_id = "snapshot-one"
    plain_evidence = {plain_id: _snapshot_record(RUN_A, evidence_id=plain_id)}
    plain_arguments = {
        "bull-1": {
            **_identity(RUN_A),
            "argument_id": "bull-1",
            # v1 spelling of the argument body; C1 requires a nonempty claim.
            "claim": "Price holds above the Bollinger upper band.",
            "evidence_ids": [plain_id],
        },
    }

    approved = evaluate(
        _candidate(BUY, ("bull-1",)), plain_arguments, plain_evidence, _run(RUN_A),
        results_dir=results,
    )
    assert approved.publication_status == APPROVED, approved.reason_codes

    foreign = {"bull-1": {**plain_arguments["bull-1"], "run_id": RUN_B}}
    blocked = evaluate(
        _candidate(BUY, ("bull-1",)), foreign, plain_evidence, _run(RUN_A),
        results_dir=results,
    )
    assert blocked.publication_status == BLOCKED
    assert INSUFFICIENT_EVIDENCE in blocked.reason_codes


# --- §2 row 6: the approved record --------------------------------------------


@pytest.mark.unit
def test_valid_run_approves_with_identity_and_resolved_references(results):
    """Row 6: the same-run control. Approval is the only case that reads material."""
    argument_id = _argument_id(RUN_A)
    evidence_index = _evidence_index(RUN_A)

    # The v1 fixture records carry identity and a resolvable content reference.
    record = evidence_index[_evidence_id(RUN_A)]
    assert record["run_id"] == RUN_A
    assert record["ticker"] == TICKER
    assert record["as_of_date"] == AS_OF_DATE
    assert record["contract_version"] == CONTRACT_VERSION
    assert SNAPSHOT_MATERIAL == _read_content(results, record["content_ref"])

    result = _evaluate(argument_ids=(argument_id,), results_dir=results)

    assert result.publication_status == APPROVED
    assert result.reason_codes == ()
    assert result.rating == BUY
    assert result.run_id == RUN_A
    assert argument_id in result.argument_ids
    assert _evidence_id(RUN_A) in result.evidence_ids


# --- §2 precedence: the first matching row wins -------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kwargs", "expected_code"),
    [
        # An exhausted run outranks an invalid rating and missing evidence.
        ({"status": BUDGET_EXHAUSTED, "rating": "REVIEW", "argument_ids": ()}, BUDGET_EXHAUSTED),
        # An invalid rating outranks missing evidence (row 4 before row 5).
        ({"rating": None, "argument_ids": ()}, INVALID_RATING),
    ],
    ids=["terminal-before-rating", "rating-before-evidence"],
)
def test_first_matching_gate_row_wins(gate_evaluate, kwargs, expected_code):
    result = gate_evaluate(**kwargs)
    assert result.publication_status == BLOCKED
    assert result.reason_codes[0] == expected_code or result.reason_codes == (expected_code,)


# --- unpublished results carry no candidate body -----------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": BUDGET_EXHAUSTED},
        {"rating": "REVIEW"},
        {"argument_ids": ("arg:does-not-exist",)},
        {"run": _run(RUN_B), "argument_ids": (_argument_id(RUN_A),)},
    ],
    ids=["terminal", "invalid-rating", "unknown-reference", "foreign-run"],
)
def test_blocked_result_carries_no_candidate_body(gate_evaluate, kwargs):
    """C0/C1: a refused candidate is nonofficial; its prose is not published."""
    result = gate_evaluate(**kwargs)
    assert result.publication_status == BLOCKED
    assert result.rating is None
    assert CANDIDATE_BODY not in repr(result)
    assert MARKER not in repr(result)


# --- four official sinks (T-FR01-SINKS, T-INV01-BYPASS) -----------------------


def _owner():
    """The v1 owner symbols, or a skip that names what this environment lacks.

    R8-B provides ``evaluate_publication`` and ``PublicationRequiredError``; after
    this revision the sink cases execute.
    """
    missing = [
        name for name in ("evaluate_publication", "PublicationRequiredError")
        if not hasattr(gate, name)
    ]
    if missing:
        pytest.skip(
            "publication_gate lacks " + ", ".join(missing)
            + "; the four-sink behaviour below cannot be exercised and this case is NOT a pass"
        )


def _run_state(run_id: str = RUN_A) -> dict:
    """A finished run state as the four sinks receive it: identity plus reports.

    ``course_run`` is the only field the cross-run cases change; everything else,
    including the v1 evidence/argument indexes, stays run A material.
    """
    return {
        "run_id": run_id,
        "course_run": _run(run_id),
        "company_of_interest": TICKER,
        "trade_date": AS_OF_DATE,
        "market_report": "AAPL closed at 348.245 USD.",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "investment_debate_state": {},
        "risk_debate_state": {},
        "investment_plan": "",
        "trader_investment_plan": "",
        "evidence_index": _evidence_index(RUN_A),
        "argument_index": _argument_index(RUN_A),
        "market_evidence": [],
    }


def _approved_result(results):
    _owner()
    return gate.evaluate_publication(
        _candidate(BUY, (_argument_id(RUN_A),)),
        _argument_index(RUN_A),
        _evidence_index(RUN_A),
        _run(RUN_A),
        results_dir=results,
    )


def _blocked_result(results):
    _owner()
    return gate.evaluate_publication(
        _candidate(BUY, ()), {}, _evidence_index(RUN_A), _run(RUN_A),
        results_dir=results,
    )


def _foreign_blocked_result(results):
    """A BLOCKED result whose only difference from ``_approved_result`` is identity."""
    _owner()
    return gate.evaluate_publication(
        _candidate(BUY, (_argument_id(RUN_A),)),
        _argument_index(RUN_A),
        _evidence_index(RUN_A),
        _run(RUN_B),
        results_dir=results,
    )


def _make_graph(monkeypatch, tmp_path, models=None, config_extra=None):
    """A real ``TradingAgentsGraph`` with fake models and isolated paths.

    The graph object, its wiring, its gate dispatch and its sinks are the
    production code. Only the model clients (both tiers) and the ticker-identity
    lookup are replaced, so ``propagate()`` runs the whole graph offline against
    fixed scripted answers and never reaches a vendor.
    """
    import tradingagents.graph.trading_graph as tg
    from tradingagents.default_config import DEFAULT_CONFIG

    scripted = models if models is not None else _ScriptedModel()

    class _Client:
        def get_llm(self):
            return scripted

    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _Client())
    monkeypatch.setattr(tg, "resolve_instrument_identity", lambda t: {
        "company_name": "Apple Inc.", "sector": "Technology",
        "industry": "Consumer Electronics", "exchange": "NASDAQ", "quote_type": "EQUITY",
    })
    config = dict(DEFAULT_CONFIG)
    config.update({
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "checkpoint_enabled": False,
    })
    if config_extra:
        config.update(config_extra)
    return tg.TradingAgentsGraph(selected_analysts=("market",), debug=False, config=config)


# --- scripted model ------------------------------------------------------------

# The Portfolio Manager's candidate text. It is what the gate releases on
# APPROVAL, so its marker is the body INV-01 keeps out of every surface.
CANDIDATE_TEXT = CANDIDATE_BODY

# The analyst report the run produces; the graph indexes it as run material.
MARKET_REPORT = "AAPL closed at 348.245 USD on 2026-11-10; the uptrend is intact."


EVIDENCE_ID_RE = r"ev:[^\s,;&|()\[\]<>\"']+"
ARGUMENT_ID_RE = r"arg:(?:bull|bear):[^\s,;&|()\[\]<>\"']+"


def _schema_answer(prompt) -> tuple[str, str, list[str]]:
    """The structured call's prompt text, its lowercase form, and the evidence ids it shows."""
    text = _prompt_text(prompt)
    return text, text.lower(), re.findall(EVIDENCE_ID_RE, text)


def _schema_instance(owner, schema, prompt):
    """Build the schema instance that answers this step."""
    from tradingagents.agents.schemas import (
        PortfolioDecision,
        PortfolioRating,
        ResearchPlan,
        TraderAction,
        TraderProposal,
    )

    text, low, evidence = _schema_answer(prompt)
    name = getattr(schema, "__name__", "")

    if name == "DebateArgument":
        cited = []
        if owner.cite_evidence and evidence:
            snapshot = [e for e in evidence if "market_snapshot" in e]
            if owner.cite_snapshot_only and snapshot:
                cited = [snapshot[0]]
            elif not owner.cite_snapshot_only:
                cited = [evidence[0]]
        return schema(argument=owner.answer(prompt), evidence_ids=cited)
    if name == "ResearchPlan":
        # Only the Research Manager asks for a plan. Answering another agent's
        # prompt with one would fabricate a plan from an analyst report, so the
        # role is checked rather than assumed.
        assert "research manager" in low, (
            "the scripted model was asked for a ResearchPlan outside the Research "
            f"Manager step; prompt begins: {text[:200]!r}"
        )
        return ResearchPlan(
            recommendation=PortfolioRating.BUY,
            rationale="The bull case held against the bear's risks.",
            strategic_actions="Hold the position and re-check the trend next session.",
        )
    if name == "TraderProposal":
        return TraderProposal(action=TraderAction.HOLD, reasoning="The trend is intact.")
    if name == "PortfolioDecision":
        # The accepted-argument ids the Portfolio Manager prompt lists.
        accepted = re.findall(ARGUMENT_ID_RE, text)
        return PortfolioDecision(
            rating=PortfolioRating.BUY,
            argument_ids=accepted if owner.cite_evidence else [],
            executive_summary="Add on the breakout, small size.",
            investment_thesis=f"{MARKER} price holds above the Bollinger upper band.",
        )
    raise AssertionError(f"the scripted model has no answer for schema {name or schema!r}")


class _SchemaBound:
    """A ``with_structured_output(schema)`` view answering with real schema instances.

    The agents that ask for typed output (Bull/Bear researchers, Research
    Manager, Trader, Portfolio Manager) get a validated object built from the
    same scripted answers as the free-text path, so a run can cite evidence and
    return a candidate without any provider.
    """

    def __init__(self, owner, schema):
        self.owner = owner
        self.schema = schema

    def invoke(self, prompt, *a, **k):
        return _schema_instance(self.owner, self.schema, prompt)


class _ScriptedModel:
    """A deterministic chat model for every agent of the graph.

    Each graph step is answered from the prompt it is given: the Bull cites the
    evidence id in the run's evidence menu, the Portfolio Manager returns a Buy
    candidate, the analyst writes its report. ``bind_tools`` never emits a tool
    call unless ``call_snapshot`` is set, in which case the market analyst really
    calls ``get_verified_market_snapshot`` on its first turn and then reports.
    """

    def __init__(self, cite_evidence: bool = True, call_snapshot: bool = False,
                 cite_snapshot_only: bool = False):
        self.cite_evidence = cite_evidence
        self.call_snapshot = call_snapshot
        # Cite only evidence that names a market snapshot: proves the citation
        # resolves through the retained material, not through the report record.
        self.cite_snapshot_only = cite_snapshot_only
        self.calls: list[str] = []
        self.evidence_ids_seen: list[str] = []
        self.snapshot_calls = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def bind_tools(self, tools, **kwargs):
        return RunnableLambda(_BoundModel(self))

    def with_structured_output(self, schema, **kwargs):
        return _SchemaBound(self, schema)

    def invoke(self, messages, *a, **k):
        from langchain_core.messages import AIMessage

        return AIMessage(content=self.answer(messages))

    def answer(self, messages) -> str:
        """The scripted answer for this step, choosing the role from the prompt.

        The analyst and researcher checks come **before** the downstream roles:
        the market analyst's prompt mentions "traders" in its instructions and the
        Bull's prompt quotes the market report, so a later check would answer the
        wrong role. The Research Manager is the only agent that asks for a
        ``ResearchPlan``, and it is matched on its own title.
        """
        text = _prompt_text(messages)
        self.calls.append(text)
        low = text.lower()

        # The Bull researcher is handed the run's evidence menu; cite what it shows.
        evidence = re.findall(EVIDENCE_ID_RE, text)
        if evidence:
            self.evidence_ids_seen.extend(evidence)

        # Analyst first: its own report, never a downstream plan. The analyst's
        # prompt opens "You are a trading assistant" and lists its indicator tools;
        # the Bull/Bear prompts quote other agents' text, so they are matched on
        # their own opening line below.
        if "you are a trading assistant" in low or "you are a market analyst" in low:
            return MARKET_REPORT

        is_bull = "you are a bull analyst" in low
        is_bear = "you are a bear analyst" in low
        if is_bull:
            return "Bull case: price held the breakout."
        if is_bear:
            return "Bear case: the move is extended."

        if "research manager" in low:
            return (
                f"**Recommendation**: {BUY}\n\n"
                "**Rationale**: The bull case held against the bear's risks.\n\n"
                "**Strategic Actions**: Hold the position and re-check the trend."
            )
        if "portfolio manager" in low or "final trading decision" in low:
            return CANDIDATE_TEXT
        if "trader" in low or "trading plan" in low:
            return "Plan: hold the position into the next session."
        if "risk" in low or "aggressive" in low or "conservative" in low or "neutral" in low:
            return "Risk view: size stays moderate."
        return "Acknowledged."


class _BoundModel:
    """A model with tools bound that never calls one.

    ``take_turn`` pipes its prompt into this object as ``prompt | llm``, so the
    bound branch must be a ``Runnable`` that accepts the prompt value — a plain
    object with only ``invoke`` fails LangChain's coercion. Each branch is a
    ``RunnableLambda`` that converts the prompt to its message list and defers to
    the scripted model, the same shape the market test's validated fake uses.
    """

    def __init__(self, owner):
        self.owner = owner

    def _answer(self, prompt):
        to_messages = getattr(prompt, "to_messages", None)
        messages = to_messages() if callable(to_messages) else prompt
        return self.owner.answer(messages)

    def invoke(self, prompt, *a, **k):
        from langchain_core.messages import AIMessage

        text = self._prompt_text(prompt)
        low = text.lower()
        # The market analyst's prompt opens "You are a trading assistant" and lists
        # its indicator tools. "market report" / "ohlcv" are kept as fallbacks for a
        # future prompt, but the analyst never says "market analyst", so matching on
        # that alone would skip the tool call and starve the run of evidence.
        is_market = (
            "you are a trading assistant" in low
            or "market analyst" in low
            or "market report" in low
            or "ohlcv" in low
        )
        if self.owner.call_snapshot and is_market and self.owner.snapshot_calls == 0:
            # The analyst's first turn is a real tool call. The ToolNode injects
            # ``symbol``/``trade_date`` from the graph state, so the model sends
            # only the two model-facing arguments.
            self.owner.snapshot_calls += 1
            self.owner.calls.append(text)
            return AIMessage(content="", tool_calls=[{
                "name": "get_verified_market_snapshot",
                "args": {"curr_date": AS_OF_DATE, "look_back_days": 7},
                "id": "call-1",
            }])
        return AIMessage(content=self._answer(prompt))

    def _prompt_text(self, prompt) -> str:
        to_messages = getattr(prompt, "to_messages", None)
        messages = to_messages() if callable(to_messages) else prompt
        return _prompt_text(messages)

    # ``prompt | bound`` treats the right-hand side as a runnable: it is called,
    # not only asked to ``invoke``.
    __call__ = invoke


def _prompt_text(messages) -> str:
    """All message text of a prompt, flattened, for role detection.

    Accepts what the production call sites actually pass: a ``PromptValue`` (the
    pipe's input), a list of messages, or a bare string (the researchers hand
    ``invoke_structured`` an f-string). A ``PromptValue`` is converted to its
    messages; a string is its own text. Reading a bare string as a message would
    yield an empty ``content`` and silently hide the evidence menu.
    """
    to_messages = getattr(messages, "to_messages", None)
    if callable(to_messages):
        messages = to_messages()
    elif isinstance(messages, str):
        return messages
    parts = []
    for message in messages:
        if isinstance(message, str):
            parts.append(message)
            continue
        content = getattr(message, "content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(str(c) for c in content if isinstance(c, str))
    return "\n".join(parts)


def _registered_evidence_id(run_id: str) -> str:
    """The evidence id the graph mints for this run's market report (production rule)."""
    return f"ev:{run_id}:market_report"


def _publish(graph, state) -> dict:
    """Run the real ``graph.publish()`` and return the state it wrote.

    Kept for the publish-level checks (the gate's internals); the sink cases use
    the full ``propagate()`` path below.
    """
    status = graph.publish(state)
    assert status in (APPROVED, BLOCKED), f"publish() returned {status!r}"
    return state


def _propagate(graph, models: _ScriptedModel, status: str) -> dict:
    """Run the real ``propagate()`` end to end and return ``(final_state, signal)``.

    The scripted models are swapped for this run only; everything else —
    the analysts, the Index Evidence step, the debate, the gate and the sinks —
    is production code.
    """
    graph.quick_thinking_llm = models
    graph.deep_thinking_llm = models
    graph.graph_setup.quick_thinking_llm = models
    graph.graph_setup.deep_thinking_llm = models
    graph.reflector = _NoopReflector()
    final_state, signal = graph.propagate(TICKER, AS_OF_DATE)
    assert isinstance(final_state, dict), f"propagate() returned {type(final_state)}"
    assert final_state.get("publication_status") == status, (
        f"expected the gate to return {status}, got "
        f"{final_state.get('publication_status')!r} ({final_state.get('publication_reason')!r})"
    )
    return final_state, signal


class _NoopReflector:
    """A reflector that never calls the model: settlement is not under test here."""

    def __init__(self, *a, **k):
        pass

    def reflect_on_decision(self, *a, **k):
        return None

    def __getattr__(self, name):
        def _noop(*a, **k):
            return None

        return _noop


def _files(root) -> list:
    root = Path(root)
    if not root.exists():
        return []
    return sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file())


def _text(root, files, suffixes) -> str:
    root = Path(root)
    return "\n".join(
        (root / p).read_text(encoding="utf-8", errors="replace")
        for p in files if Path(p).suffix in suffixes
    )


def _decision_file_in(files) -> bool:
    return any(Path(p).parts[-2:] == ("5_portfolio", "decision.md") for p in files)


# --- the chain the gate reasons over, before any sink --------------------------


@pytest.mark.unit
def test_gate_record_carries_identity_and_resolved_chain(monkeypatch, tmp_path):
    """§1–§3: publish() writes the run's identity and its resolved evidence chain.

    A finished run's state: the evidence lives in the v1 ``evidence_id -> record``
    mapping, the accepted argument in the authoritative ``argument_index``, and
    the candidate cites that argument. The argument is **not** placed in the
    legacy ``evidence_index.arguments`` view — that view is not a release
    authority, so a run whose only argument lives there cannot publish.
    ``publish()`` must resolve candidate -> argument_index -> evidence_index ->
    retained material and write the one gate verdict with that chain.
    """
    _owner()
    graph = _make_graph(monkeypatch, tmp_path)
    state = _run_state()
    state["course_run"] = {**_run(RUN_A), "execution_status": COMPLETED}
    evidence_id = _registered_evidence_id(RUN_A)
    argument_id = _argument_id(RUN_A)
    results_dir = Path(tmp_path / "results")
    material = _write_material(results_dir)
    # The same complete snapshot record the positive controls use, under the id
    # this case cites: every C1 required field is present, and its ``content_ref``
    # names the run A material just written.
    state["evidence_index"] = {
        "run_id": RUN_A,
        "evidence": {
            evidence_id: _snapshot_record(
                RUN_A, evidence_id=evidence_id,
                content_ref=f"evidence://{RUN_A}/{material.name}",
            ),
        },
    }
    # The authoritative argument index the researchers write: a bare
    # argument_id -> record mapping, every record carrying the run's full identity.
    state["argument_index"] = {
        argument_id: {
            "argument_id": argument_id,
            "speaker": "Bull Analyst",
            "claim": "Bull Analyst: price held the breakout.",
            "evidence_ids": [evidence_id],
            **_identity(RUN_A),
        },
    }
    state["candidate_rating"] = BUY
    state["candidate_decision"] = CANDIDATE_TEXT
    state["candidate_argument_ids"] = [argument_id]

    _publish(graph, state)

    assert state["publication_status"] == APPROVED, state.get("publication_reason")
    assert state.get("final_rating") == BUY
    chain = state.get("publication_chain") or []
    assert chain, "an approved run records the resolved (argument, evidence) chain"
    assert tuple(chain[0][:2]) == (argument_id, evidence_id), chain
    # The resolved evidence is the record the authoritative mapping holds.
    assert state["evidence_index"]["evidence"][evidence_id]["content_ref"].endswith(
        material.name
    )


@pytest.mark.unit
def test_argument_only_in_the_legacy_view_does_not_publish(monkeypatch, tmp_path):
    """C1: ``evidence_index.arguments`` is the compatibility view, not a release authority.

    The identical accepted argument approves from ``argument_index``; moved into
    the legacy ``evidence_index.arguments`` list and removed from the
    authoritative mapping, the candidate resolves nothing and is refused.
    """
    _owner()
    graph = _make_graph(monkeypatch, tmp_path)
    state = _run_state()
    state["course_run"] = {**_run(RUN_A), "execution_status": COMPLETED}
    evidence_id = _registered_evidence_id(RUN_A)
    argument_id = _argument_id(RUN_A)
    results_dir = Path(tmp_path / "results")
    material = _write_material(results_dir)
    evidence_record = _snapshot_record(
        RUN_A, evidence_id=evidence_id, content_ref=f"evidence://{RUN_A}/{material.name}"
    )
    argument_record = {
        "argument_id": argument_id,
        "speaker": "Bull Analyst",
        "claim": "Bull Analyst: price held the breakout.",
        "evidence_ids": [evidence_id],
        **_identity(RUN_A),
    }
    state["evidence_index"] = {
        "run_id": RUN_A,
        "evidence": {evidence_id: evidence_record},
        "arguments": [{**argument_record, "id": argument_id}],
    }
    state["argument_index"] = {}
    state["candidate_rating"] = BUY
    state["candidate_decision"] = CANDIDATE_TEXT
    state["candidate_argument_ids"] = [argument_id]

    positive = _publish(graph, {**state, "argument_index": {argument_id: argument_record}})
    assert positive["publication_status"] == APPROVED, positive.get("publication_reason")

    _publish(graph, state)

    assert state["publication_status"] == BLOCKED, (
        "an argument that exists only in the legacy evidence_index.arguments view "
        "was treated as a release authority"
    )
    assert state.get("final_rating") in (None, "")
    assert MARKER not in repr(state.get("final_trade_decision"))


@pytest.mark.unit
def test_foreign_run_evidence_is_blocked_at_the_gate(results):
    """§2 row 5: run A's evidence cited in run B does not resolve, so no rating.

    Only the ``RunContext`` changes; the candidate, the argument index and the
    evidence index are the same material the same-run control approves.
    """
    blocked = _foreign_blocked_result(results)
    assert blocked.publication_status == BLOCKED
    assert INSUFFICIENT_EVIDENCE in blocked.reason_codes
    assert blocked.rating is None
    assert MARKER not in repr(blocked)

    approved = _approved_result(results)
    assert approved.publication_status == APPROVED, approved.reason_codes
    assert approved.rating == BUY


# --- sink 1: the Python return of propagate() ----------------------------------


@pytest.mark.unit
def test_propagate_returns_the_final_state_and_rating(monkeypatch, tmp_path):
    """Sink 1: the caller of ``propagate()`` gets the gated final state and rating.

    The gate approves on the run's own retained tool evidence: the analyst really
    calls the snapshot tool, the subgraph retains the response, and the Bull cites
    that material. The chain the caller receives must therefore resolve through
    the snapshot record, not through a fixture or a report.
    """
    _owner()
    _pin_snapshot(monkeypatch)
    models = _ScriptedModel(call_snapshot=True, cite_snapshot_only=True)
    graph = _make_graph(monkeypatch, tmp_path, models)

    final_state, signal = _propagate(graph, models, APPROVED)

    # The run's identity and the gate's verdict are in the caller's state.
    assert final_state.get("publication_status") == APPROVED
    assert final_state.get("final_rating") == BUY
    assert signal == BUY, f"the caller's signal must be the approved rating, got {signal!r}"

    # The evidence chain the gate resolved belongs to this run.
    assert final_state.get("run_id"), "propagate() must carry the run id"
    chain = final_state.get("publication_chain") or []
    assert chain, "an approved run must record its resolved chain"
    evidence = (final_state.get("evidence_index") or {}).get("evidence") or {}
    assert isinstance(evidence, dict) and evidence, (
        f"the run must index its retained evidence as a mapping: {type(evidence).__name__}"
    )
    snapshot_ids = {
        evidence_id for evidence_id, record in evidence.items()
        if (record.get("source_kind") or "") == "market_snapshot"
    }
    assert snapshot_ids, f"the run indexed no snapshot evidence: {sorted(evidence)}"
    assert any(link[1] in snapshot_ids for link in chain), (
        f"the approved chain does not resolve through the retained snapshot: {chain}"
    )
    assert MARKER in final_state.get("final_trade_decision", "")


@pytest.mark.unit
def test_propagate_blocked_run_returns_no_rating_or_body(monkeypatch, tmp_path):
    """Sink 1 negative: a run whose candidate cites nothing returns no rating."""
    _owner()
    models = _ScriptedModel(cite_evidence=False)
    graph = _make_graph(monkeypatch, tmp_path, models)

    final_state, signal = _propagate(graph, models, BLOCKED)

    assert final_state.get("publication_status") == BLOCKED
    assert final_state.get("final_rating") in (None, "")
    assert final_state.get("final_trade_decision") in (None, "")
    assert MARKER not in repr(final_state)
    # The blocked run's own reports are still there: only the candidate is withheld.
    assert MARKET_REPORT in final_state.get("market_report", "")
    assert signal != BUY


# --- R8-B §4: the real snapshot chain reaches publication ----------------------


def _pin_snapshot(monkeypatch):
    """Serve a fixed OHLCV frame in place of the vendor download for this test.

    Only that one call inside the snapshot builder is replaced; the real tool
    closure, the real snapshot rendering and the real ``as_of`` clamp run, so a
    tool call in the graph produces genuine snapshot text that can be retained.
    """
    import pandas as pd

    import tradingagents.dataflows.vendors.yahoo.snapshot as snapshot

    frame = pd.DataFrame(
        [
            {"Date": d, "Open": o, "High": h, "Low": low, "Close": c, "Volume": v}
            for d, o, h, low, c, v in (
                ("2026-11-04", 341.10, 344.20, 340.05, 344.02, 51_200_000),
                ("2026-11-05", 344.02, 347.80, 343.10, 347.55, 49_800_000),
                ("2026-11-06", 347.55, 350.10, 346.20, 349.90, 52_500_000),
                ("2026-11-09", 349.90, 352.30, 348.80, 351.60, 47_300_000),
                ("2026-11-10", 351.60, 353.40, 347.90, 348.245, 55_100_000),
            )
        ],
        columns=["Date", "Open", "High", "Low", "Close", "Volume"],
    )
    monkeypatch.setattr(snapshot, "load_ohlcv", lambda *a, **k: frame.copy())


@pytest.mark.unit
def test_real_snapshot_run_approves_through_retention_index_argument_and_publish(
        monkeypatch, tmp_path):
    """End-to-end positive: tool call -> retention -> index -> argument -> publish.

    The market analyst really calls ``get_verified_market_snapshot`` inside its
    subgraph, the subgraph retains the response and hands the receipt up, the
    Index Evidence step folds it into the run's index, the Bull cites it, the
    Portfolio Manager's candidate cites the accepted argument, and the gate
    approves only after re-reading the retained material.
    """
    _owner()
    _pin_snapshot(monkeypatch)
    models = _ScriptedModel(call_snapshot=True, cite_snapshot_only=True)
    graph = _make_graph(monkeypatch, tmp_path, models)

    final_state, signal = _propagate(graph, models, APPROVED)

    assert models.snapshot_calls >= 1, "the market analyst never called the snapshot tool"
    receipts = final_state.get("market_evidence") or []
    assert receipts, "the subgraph returned no snapshot receipt to the parent graph"

    # The receipt is part of the run's index and its material is retained.
    evidence = (final_state.get("evidence_index") or {}).get("evidence") or {}
    assert isinstance(evidence, dict), (
        "the Index Evidence step must build an evidence_id -> record mapping, "
        f"not a list the gate has to search: {type(evidence).__name__}"
    )
    snapshot_ids = [
        evidence_id for evidence_id, record in evidence.items()
        if (record.get("source_kind") or "") == "market_snapshot"
    ]
    assert snapshot_ids, f"the snapshot was not indexed: {sorted(evidence)}"
    for record in evidence.values():
        if record.get("content_ref"):
            from tradingagents.agents.evidence_collection import resolve_content_ref

            material = resolve_content_ref(
                record["content_ref"], graph.config["results_dir"], record
            )
            assert material, f"indexed material does not resolve: {record['content_ref']}"

    # The approved chain runs through the retained snapshot, not the report.
    chain = final_state.get("publication_chain") or []
    assert chain, "an approved run records its resolved chain"
    assert any(link[1] in snapshot_ids for link in chain), (
        f"the approved chain did not resolve through the retained snapshot: {chain}"
    )
    assert final_state.get("final_rating") == BUY
    assert signal == BUY


@pytest.mark.unit
def test_report_only_run_does_not_approve(monkeypatch, tmp_path):
    """Negative: a run with only ``market_report`` and no snapshot never publishes.

    The analyst writes its report and takes no tool call, so nothing is retained
    and the evidence index is empty. A report is not evidence: with no retained
    material the Bull has nothing citable, so no argument is accepted and the
    candidate cannot resolve any reference.
    """
    _owner()
    models = _ScriptedModel(call_snapshot=False)
    graph = _make_graph(monkeypatch, tmp_path, models)

    final_state, signal = _propagate(graph, models, BLOCKED)

    assert models.snapshot_calls == 0
    assert not (final_state.get("market_evidence") or [])
    assert final_state.get("publication_status") == BLOCKED
    assert INSUFFICIENT_EVIDENCE in (final_state.get("publication_result") or {}).get(
        "reason_codes", []
    ), final_state.get("publication_result")
    assert final_state.get("final_rating") in (None, "")
    assert MARKER not in repr(final_state)
    assert signal != BUY


@pytest.mark.unit
def test_snapshot_whose_material_expired_does_not_approve(monkeypatch, tmp_path):
    """Negative: a snapshot whose retained material is gone cannot back a release.

    The positive control runs the real chain and approves; the same run's retained
    material is then deleted and the gate is re-run on the finished state, which
    must refuse because the cited evidence no longer resolves.
    """
    _owner()
    _pin_snapshot(monkeypatch)
    models = _ScriptedModel(call_snapshot=True, cite_snapshot_only=True)
    graph = _make_graph(monkeypatch, tmp_path, models)
    final_state, _signal = _propagate(graph, models, APPROVED)

    results_dir = Path(graph.config["results_dir"])
    retained = sorted(results_dir.rglob("*.md"))
    assert retained, f"the approved run retained no material under {results_dir}"
    for path in retained:
        path.unlink()

    # Re-judge the same finished state with the gate's own entry point.
    from tradingagents.graph.publication_gate import (
        evaluate_publication,
        publication_run,
    )

    result = evaluate_publication(
        {
            "rating": final_state.get("candidate_rating") or final_state.get("final_rating"),
            "argument_ids": final_state.get("candidate_argument_ids") or (),
        },
        final_state.get("argument_index") or {},
        final_state.get("evidence_index") or {},
        publication_run(final_state),
        results_dir=graph.config["results_dir"],
    )
    assert result.publication_status == BLOCKED, (
        "evidence whose retained material expired must not publish"
    )
    assert INSUFFICIENT_EVIDENCE in result.reason_codes


# --- sink 2: the saved report tree ---------------------------------------------


@pytest.mark.unit
def test_propagate_approved_report_writes_rating_body_and_decision(monkeypatch, tmp_path):
    """Sink 2 positive: the propagate() state saves a full official report.

    Uses the real-snapshot configuration: the analyst really calls the snapshot
    tool, the subgraph retains the response, and the Bull cites that retained
    material. The report tree is therefore written from an approval the gate
    reached on actual tool evidence, not from a fixture-supplied record.
    """
    _owner()
    _pin_snapshot(monkeypatch)
    models = _ScriptedModel(call_snapshot=True, cite_snapshot_only=True)
    graph = _make_graph(monkeypatch, tmp_path, models)
    final_state, _signal = _propagate(graph, models, APPROVED)

    save_path = tmp_path / "reports"
    graph.save_reports(final_state, TICKER, save_path=save_path)

    files = _files(save_path)
    markdown = _text(save_path, files, (".md",))
    html = _text(save_path, files, (".html",))
    assert files, "an approved run must write the report tree"
    assert f"**Rating**: {BUY}" in markdown
    assert MARKER in markdown
    assert MARKER in html
    assert _decision_file_in(files), "an approved run writes 5_portfolio/decision.md"


@pytest.mark.unit
def test_propagate_blocked_report_writes_markdown_and_html_diagnostics(monkeypatch, tmp_path):
    """Sink 2 negative: a BLOCKED run writes both diagnostics, without the candidate.

    The diagnostic report must exist as Markdown **and** HTML, state BLOCKED,
    and carry no official rating, no candidate body and no ``decision.md``.
    """
    _owner()
    models = _ScriptedModel(cite_evidence=False)
    graph = _make_graph(monkeypatch, tmp_path, models)
    final_state, _signal = _propagate(graph, models, BLOCKED)

    save_path = tmp_path / "reports"
    graph.save_reports(final_state, TICKER, save_path=save_path)

    files = _files(save_path)
    markdown = _text(save_path, files, (".md",))
    html = _text(save_path, files, (".html",))

    assert any(p.suffix == ".md" for p in files), (
        f"a blocked run must still write its Markdown diagnostic; wrote {files}"
    )
    assert any(p.suffix == ".html" for p in files), (
        f"a blocked run must still write its HTML diagnostic; wrote {files}"
    )
    assert not _decision_file_in(files), f"a blocked run wrote 5_portfolio/decision.md: {files}"
    assert BLOCKED in markdown, f"the diagnostic must state BLOCKED:\n{markdown[:800]}"
    assert BLOCKED in html, "the HTML diagnostic must state BLOCKED"
    assert f"**Rating**: {BUY}" not in markdown
    assert "Rating: Buy" not in markdown
    assert f">{BUY}<" not in html
    assert MARKER not in markdown
    assert MARKER not in html
    # The analyst's own material is still there: the report is diagnostic, not empty.
    assert "AAPL" in markdown


# --- sink 3: decision memory ---------------------------------------------------


@pytest.mark.unit
def test_propagate_approved_run_is_written_to_decision_memory(monkeypatch, tmp_path):
    """Sink 3 positive: propagate() records the approved decision in memory.

    Runs the real-snapshot configuration, so the entry that reaches decision
    memory comes from a gate approval backed by retained tool evidence. The
    entry is a dict: its rating, ticker, date and decision body must all be this
    run's official ones, not the candidate's untrusted text.
    """
    _owner()
    _pin_snapshot(monkeypatch)
    models = _ScriptedModel(call_snapshot=True, cite_snapshot_only=True)
    graph = _make_graph(monkeypatch, tmp_path, models)
    final_state, _signal = _propagate(graph, models, APPROVED)

    entries = graph.memory_log.load_entries()
    assert entries, "an approved decision must reach decision memory"
    approved = [entry for entry in entries if entry["rating"] == BUY]
    assert approved, f"no memory entry carries the approved rating: {entries}"
    entry = approved[-1]
    assert entry["ticker"] == TICKER
    assert entry["date"] == AS_OF_DATE
    assert MARKER in entry["decision"], (
        f"the approved candidate body did not reach decision memory: {entry['decision']!r}"
    )
    # The entry is this run's official decision, not the internal candidate.
    assert final_state.get("final_rating") == BUY
    assert entry["decision"] == final_state.get("final_trade_decision")


@pytest.mark.unit
def test_propagate_blocked_run_is_not_written_to_decision_memory(monkeypatch, tmp_path):
    """Sink 3 negative: a BLOCKED run writes nothing to decision memory."""
    _owner()
    models = _ScriptedModel(cite_evidence=False)
    graph = _make_graph(monkeypatch, tmp_path, models)
    _propagate(graph, models, BLOCKED)

    entries = graph.memory_log.load_entries()
    assert entries == [], f"a BLOCKED decision reached decision memory: {entries}"
    assert MARKER not in repr(entries)


# --- sink 4: the CLI -----------------------------------------------------------


def _cli_sink(monkeypatch, tmp_path, models, status) -> tuple[str, dict]:
    """Run the real CLI entry over a real graph and return ``(display, final_state)``.

    The graph is the production ``TradingAgentsGraph`` (only its models are
    scripted), so the CLI's stream, its gate call and its display all run. The
    live view is replaced by a null context, the console records text, and the
    graph object the CLI built is kept so the caller can read the gated state.
    """
    from rich.console import Console

    import cli.display as display
    import cli.run as cli_run
    from cli.models import AnalystType

    graph = _make_graph(monkeypatch, tmp_path, models)
    graph.quick_thinking_llm = models
    graph.deep_thinking_llm = models
    graph.graph_setup.quick_thinking_llm = models
    graph.graph_setup.deep_thinking_llm = models
    graph.reflector = _NoopReflector()

    # The state the CLI streamed and the gate judged, captured as the CLI goes.
    runs: list[dict] = []
    publish = graph.publish

    def _capturing_publish(final_state):
        result = publish(final_state)
        runs.append(final_state)
        return result

    graph.publish = _capturing_publish

    class _NullLive:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def update(self, *a, **k):
            pass

    record = Console(record=True, width=200, force_terminal=False, color_system=None)
    monkeypatch.setattr(display, "console", record)
    monkeypatch.setattr(cli_run, "console", record)
    monkeypatch.setattr(cli_run, "TradingAgentsGraph", lambda *a, **k: graph)
    monkeypatch.setattr(cli_run, "Live", _NullLive)
    monkeypatch.setattr(cli_run.sys, "stdin", type("S", (), {"isatty": lambda s: True})())
    monkeypatch.setattr(cli_run, "get_user_selections", lambda flags=None: {
        "ticker": TICKER, "analysis_date": AS_OF_DATE,
        "analysts": [AnalystType.MARKET], "asset_type": "stock",
    })
    monkeypatch.setattr(cli_run, "_build_run_config", lambda s, c: {
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "checkpoint_enabled": False,
    })

    cli_run.run_analysis(flags={"save": False, "show": True})

    # The CLI run really reached the gate, and with the verdict under test.
    assert runs, "the CLI run never published: the graph's gate did not run"
    final_state = runs[-1]
    assert final_state.get("publication_status") == status, (
        f"expected the CLI run's gate to return {status}, got "
        f"{final_state.get('publication_status')!r} ({final_state.get('publication_reason')!r})"
    )
    return record.export_text(), final_state


@pytest.mark.unit
def test_cli_shows_approved_body(monkeypatch, tmp_path):
    """Sink 4 positive: the CLI shows an approved decision's body.

    Runs the real-snapshot configuration through the real CLI entry, so the body
    the CLI displays comes from a gate approval backed by retained tool evidence.
    """
    _owner()
    _pin_snapshot(monkeypatch)
    text, final_state = _cli_sink(
        monkeypatch, tmp_path,
        _ScriptedModel(call_snapshot=True, cite_snapshot_only=True), APPROVED,
    )
    assert final_state.get("final_rating") == BUY
    assert MARKER in text, f"the CLI did not display the approved decision:\n{text[-2000:]}"


@pytest.mark.unit
def test_cli_shows_blocked_without_the_candidate(monkeypatch, tmp_path):
    """Sink 4 negative: the CLI shows BLOCKED and never the candidate text."""
    _owner()
    text, final_state = _cli_sink(
        monkeypatch, tmp_path, _ScriptedModel(cite_evidence=False), BLOCKED,
    )
    assert final_state.get("final_rating") in (None, "")
    assert BLOCKED in text, f"the CLI did not show the BLOCKED status:\n{text[-2000:]}"
    assert MARKER not in text
    assert f"**Rating**: {BUY}" not in text


# --- refused sinks: no gate result, no formal surface --------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "forged", [None, APPROVED], ids=["missing-result", "forged-flat-approval"],
)
def test_ungated_or_forged_approved_state_is_refused_by_typed_error(
        monkeypatch, tmp_path, forged):
    """§6 A-11 / note §2.3: a state that never passed the gate writes nothing.

    ``propagate()`` is not run: the state is the legacy writer's input, with the
    candidate body and a rating, plus an optional forged flat ``APPROVED``. Only
    the typed gate error counts as the refusal.
    """
    _owner()
    graph = _make_graph(monkeypatch, tmp_path)
    state = {
        **_run_state(),
        # What the legacy writer used to publish straight from.
        "final_rating": BUY,
        "final_trade_decision": CANDIDATE_BODY,
    }
    if forged is not None:
        state["publication_status"] = forged
    save_path = tmp_path / "reports"

    try:
        graph.save_reports(state, TICKER, save_path=save_path)
    except gate.PublicationRequiredError:
        pass
    except BaseException as exc:  # any other failure is not the expected refusal
        pytest.fail(
            f"expected publication_gate.PublicationRequiredError, got {type(exc).__name__}: {exc}",
            pytrace=False,
        )
    else:
        pytest.fail(
            "save_reports() accepted a state without a real publication_result; "
            "the typed refusal was not raised"
        )

    files = _files(save_path)
    markdown = _text(save_path, files, (".md",))
    assert not _decision_file_in(files)
    assert f"**Rating**: {BUY}" not in markdown
    assert MARKER not in markdown
