"""FR-01 publication gate — unit tests on the deterministic chain checks.

These exercise ``tradingagents.graph.publication_gate`` directly with fixed,
in-memory material (no model, no network). They cover the normal case and each
negative case from the D1 acceptance criteria: invalid rating, missing reference,
unknown id, cross-run reference, and missing/unparseable evidence.

Expected after implementation: all pass. Before implementation the module did not
exist, so these tests could not run (import error) — they are behaviour tests, not
the baseline counterexample.
"""

from __future__ import annotations

import pytest

from tradingagents.graph import publication_gate as gate

RATINGS = gate.RATINGS_5_TIER


def _state(run_reports=None):
    """A minimal run state with the given analyst reports."""
    return dict(run_reports or {})


@pytest.mark.unit
def test_valid_rating_with_resolvable_evidence_is_approved():
    index = gate.build_evidence_index("run-1", _state({
        "market_report": "Price broke out above the 50-day average.",
    }))
    ev = index.evidence_ids[0]
    assert index.accept(gate.ArgumentRecord(
        argument_id="arg:bull:1", speaker="Bull Analyst", text="breakout",
        evidence_ids=(ev,),
    ))

    outcome = gate.evaluate(index, "Buy", ("arg:bull:1",))

    assert outcome.status == gate.APPROVED
    assert outcome.rating == "Buy"
    assert outcome.resolved_chain == (("arg:bull:1", ev, "market_report"),)


@pytest.mark.unit
def test_invalid_rating_is_blocked_with_invalid_rating():
    index = gate.build_evidence_index("run-1", _state({"market_report": "text"}))
    outcome = gate.evaluate(index, "Strong Buy", ())
    assert outcome.status == gate.BLOCKED
    assert outcome.reason == gate.INVALID_RATING


@pytest.mark.unit
def test_missing_reference_is_blocked_with_insufficient_evidence():
    index = gate.build_evidence_index("run-1", _state({"market_report": "text"}))
    outcome = gate.evaluate(index, "Buy", ())
    assert outcome.status == gate.BLOCKED
    assert outcome.reason == gate.INSUFFICIENT_EVIDENCE


@pytest.mark.unit
def test_unknown_argument_id_is_blocked():
    index = gate.build_evidence_index("run-1", _state({"market_report": "text"}))
    outcome = gate.evaluate(index, "Buy", ("arg:does-not-exist",))
    assert outcome.status == gate.BLOCKED
    assert outcome.reason == gate.INSUFFICIENT_EVIDENCE


@pytest.mark.unit
def test_unknown_evidence_id_is_not_accepted():
    index = gate.build_evidence_index("run-1", _state({"market_report": "text"}))
    assert index.accept(gate.ArgumentRecord(
        argument_id="arg:bull:1", speaker="Bull Analyst", text="x",
        evidence_ids=("ev:other-run:market_report",),
    )) is False
    assert index.argument_ids == ()


@pytest.mark.unit
def test_cross_run_reference_is_blocked():
    run_a = gate.build_evidence_index("run-A", _state({"market_report": "a"}))
    ev_a = run_a.evidence_ids[0]
    # An argument minted in run A cannot be accepted in run B.
    run_b = gate.build_evidence_index("run-B", _state({"market_report": "b"}))
    assert run_b.accept(gate.ArgumentRecord(
        argument_id="arg:bull:1", speaker="Bull Analyst", text="x", evidence_ids=(ev_a,),
    )) is False
    outcome = gate.evaluate(run_b, "Buy", ("arg:bull:1",))
    assert outcome.status == gate.BLOCKED
    assert outcome.reason == gate.INSUFFICIENT_EVIDENCE


@pytest.mark.unit
def test_missing_evidence_material_yields_no_index():
    index = gate.build_evidence_index("run-1", _state({"market_report": "   ", "news_report": ""}))
    assert index.evidence_ids == ()
    outcome = gate.evaluate(index, "Buy", ("arg:bull:1",))
    assert outcome.status == gate.BLOCKED
    assert outcome.reason == gate.INSUFFICIENT_EVIDENCE


@pytest.mark.unit
def test_invalid_rating_takes_precedence_over_missing_evidence():
    index = gate.build_evidence_index("run-1", _state({"market_report": "text"}))
    outcome = gate.evaluate(index, None, ())
    assert outcome.status == gate.BLOCKED
    assert outcome.reason == gate.INVALID_RATING


@pytest.mark.unit
def test_apply_blocks_candidate_and_hides_body():
    index = gate.build_evidence_index("run-1", _state({"market_report": "text"}))
    # The Portfolio Manager writes only the internal candidate.
    final_state = {
        "candidate_decision": "**Rating**: Buy\n\nbuy now",
        "candidate_rating": "Buy",
        "candidate_argument_ids": ["arg:bull:1"],
    }
    outcome = gate.evaluate(index, "Buy", ())
    gate.apply(outcome, final_state)

    assert final_state["publication_status"] == gate.BLOCKED
    assert final_state["publication_reason"] == gate.INSUFFICIENT_EVIDENCE
    # final_rating is emptied, not set to REVIEW (REVIEW is the API tuple member).
    assert final_state["final_rating"] == ""
    assert final_state["final_trade_decision"] == ""
    # No candidate material is left in the returned state.
    assert "candidate_decision" not in final_state
    assert "candidate_rating" not in final_state
    assert "candidate_argument_ids" not in final_state
    # REVIEW is never recorded in the returned state; it is the API tuple member only.
    assert final_state.get("final_rating") != "REVIEW"


@pytest.mark.unit
def test_apply_publishes_approved_rating_and_chain():
    index = gate.build_evidence_index("run-1", _state({"market_report": "text"}))
    ev = index.evidence_ids[0]
    index.accept(gate.ArgumentRecord("arg:bull:1", "Bull Analyst", "x", (ev,)))
    final_state = {"candidate_decision": "**Rating**: Buy\n\nbuy now", "candidate_rating": "Buy"}
    outcome = gate.evaluate(index, "Buy", ("arg:bull:1",))
    gate.apply(outcome, final_state)

    assert final_state["publication_status"] == gate.APPROVED
    assert final_state["final_rating"] == "Buy"
    assert final_state["final_trade_decision"] == "**Rating**: Buy\n\nbuy now"
    assert "candidate_decision" not in final_state
    assert final_state["publication_chain"] == [("arg:bull:1", ev, "market_report")]
