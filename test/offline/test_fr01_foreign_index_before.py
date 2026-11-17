"""FR-01 regression (before the R4 A-part fix) — a foreign run's index must not publish.

Baseline: ``712617e25a380197e38d6ee5cc4dcc7ab393cf61``. Cases: T-FR01-REFERENCE
(cross-run reference) together with INV-01 (zero rejected candidates released).

The gap this test targets: ``TradingAgentsGraph.publish(state)`` verifies the
candidate against ``evidence_index`` but never against the run identity the
piece of state says it belongs to. A complete assistant index from run A, placed
on a run B that has ``course_run.run_id == "run-B"``, therefore resolves and a
Buy is published even though none of the material belongs to run B (C0: "Evidence
and metric IDs are only resolvable inside that run").

Design (R4 A part, approved):

- ``publish(state)`` is the production entry point; nothing else is called except
  a fake model client so the graph object can be constructed without network.
- The positive and negative examples share one serialised index built from the
  same report text, the same accepted argument, the same candidate rating
  (``Buy``) and the same cited argument id. The only difference is
  ``state["course_run"]["run_id"]``; the top-level ``run_id`` is omitted from
  both, so the pair isolates C0 identity on the run context.
- Expected outcome on the starting revision: the positive passes and the negative
  fails because the old gate returns APPROVED. The negative assertions are kept
  to be fixed by the implementation, not weakened here.

No not-yet-existing interface or exception type is imported.
"""

from __future__ import annotations

import copy

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from tradingagents.graph import publication_gate as gate

# Labels from C1/C0 (approved interface contract v1.0).
APPROVED = "APPROVED"
BLOCKED = "BLOCKED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
COMPLETED = "COMPLETED"
CONTRACT_VERSION = "1.0"

BUY = "Buy"
TICKER = "AAPL"
AS_OF_DATE = "2026-11-10"
RUN_A = "course-run-A"
RUN_B = "course-run-B"

# The one piece of market material both examples share.
MARKET_REPORT = (
    "AAPL closed at 348.245 USD on 2026-11-10; the Bollinger upper band is "
    "352.771 USD, so price sits 4.526 USD below the upper band."
)

# The candidate body the Portfolio Manager would have written. It is the only
# text allowed to become the official decision, and only on APPROVED.
CANDIDATE_BODY = (
    "**Rating**: Buy\n\n"
    "**Executive Summary**: add to the position on the breakout.\n\n"
    "**Investment Thesis**: price is holding above the upper band."
)


class _UnusedModel(BaseChatModel):
    """A model that raises: these tests must not send a request."""

    @property
    def _llm_type(self) -> str:
        return "unused-fake"

    def bind_tools(self, tools, **kwargs):  # type: ignore[override]
        return self

    def _generate(self, messages, stop=None,
                  run_manager: CallbackManagerForLLMRun | None = None,
                  **kwargs) -> ChatResult:
        raise AssertionError("publish() must not call the model")


class _FakeClient:
    def __init__(self, llm):
        self._llm = llm

    def get_llm(self):
        return self._llm


def _make_graph(monkeypatch, tmp_path):
    """A real ``TradingAgentsGraph`` with a fake model client and isolated paths."""
    import tradingagents.graph.trading_graph as tg
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _FakeClient(_UnusedModel()))
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
    return tg.TradingAgentsGraph(selected_analysts=("market",), debug=False, config=config)


def _retention_material(results_dir, run_id: str) -> str:
    """Write the run's retained snapshot material and return its ``content_ref``.

    The v1 rule: evidence is retained material, not report prose. The file is
    written under the §4.3 root ``{results_dir}/{ticker}/{as_of_date}/evidence/{run_id}/``,
    so the gate can re-read it before releasing, and a reference naming another
    run resolves only if that run's material exists.
    """
    from pathlib import Path

    root = Path(results_dir) / TICKER / AS_OF_DATE / "evidence" / run_id
    root.mkdir(parents=True, exist_ok=True)
    (root / "call-1.md").write_text(MARKET_REPORT, encoding="utf-8")
    return f"evidence://{run_id}/call-1.md"


def _run_a_index_state(results_dir) -> tuple[dict, dict]:
    """The evidence and argument indexes belonging to run A (C1 v1.0 mappings).

    Both are ID -> record mappings whose records carry the full v1 identity and,
    for evidence, a ``content_ref`` that resolves under run A's retention root.
    The candidate cites the argument from the authoritative ``argument_index``.
    """
    evidence_id = f"ev:{RUN_A}:market_snapshot:call-1"
    argument_id = f"arg:bull:{RUN_A}:1"
    identity = {
        "contract_version": CONTRACT_VERSION,
        "run_id": RUN_A,
        "ticker": TICKER,
        "as_of_date": AS_OF_DATE,
    }
    evidence_index = {
        "run_id": RUN_A,
        "evidence": {
            evidence_id: {
                **identity,
                "evidence_id": evidence_id,
                "source_kind": "market_snapshot",
                # C1 v1.0 shared record: source kind/vendor, the request window and
                # the source locator are required, not optional context.
                "vendor": "yahoo",
                "source_ref": (
                    "tool:get_verified_market_snapshot?tool_call_id=call-1"
                    f";ticker={TICKER};effective_as_of={AS_OF_DATE}"
                    ";curr_date=2026-11-10;look_back_days=7"
                    ";window=2026-11-03..2026-11-10"
                ),
                "source": "market_snapshot",
                "excerpt": MARKET_REPORT[:160],
                "window_start": "2026-11-03",
                "window_end": AS_OF_DATE,
                "content_ref": _retention_material(results_dir, RUN_A),
            },
        },
    }
    argument_index = {
        argument_id: {
            **identity,
            "argument_id": argument_id,
            "speaker": "Bull Analyst",
            # The v1 spelling of the argument body.
            "claim": "breakout above the upper band",
            "evidence_ids": [evidence_id],
        },
    }
    return evidence_index, argument_index


def _course_run(run_id: str) -> dict:
    """A complete C0 run context in plain, JSON-compatible form."""
    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "ticker": TICKER,
        "as_of_date": AS_OF_DATE,
        "execution_status": COMPLETED,
        "request_limit": 40,
    }


def _state_for_current_run(current_run_id: str, results_dir) -> dict:
    """The same run A indexes and the same Buy candidate, under a chosen current run.

    ``current_run_id == RUN_A`` is the positive example; anything else means the
    indexes belong to a different run than the one being published.

    The top-level ``run_id`` is deliberately left out of both examples: only
    ``course_run.run_id`` differs, so the pair isolates the C0 identity check on
    the run context rather than on a second, parallel identity field.
    """
    evidence_index, argument_index = _run_a_index_state(results_dir)
    argument_id = next(iter(argument_index))

    return {
        # Run identity as C0 defines it: the course run context.
        "course_run": _course_run(current_run_id),
        "company_of_interest": TICKER,
        "trade_date": AS_OF_DATE,
        # The run A indexes, unchanged: same ids, same material reference,
        # same argument. Only the current run context differs.
        "evidence_index": copy.deepcopy(evidence_index),
        "argument_index": copy.deepcopy(argument_index),
        # The analyst reports of the *current* run: run B analysed nothing, so
        # the index above cannot have been produced by it.
        "market_report": MARKET_REPORT,
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        # The Portfolio Manager's candidate (internal fields only).
        "candidate_rating": BUY,
        "candidate_decision": CANDIDATE_BODY,
        "candidate_argument_ids": [argument_id],
    }


@pytest.mark.unit
def test_current_run_publishes_the_same_candidate(monkeypatch, tmp_path):
    """Positive control: when the current run IS run A, the Buy is approved."""
    graph = _make_graph(monkeypatch, tmp_path)
    state = _state_for_current_run(RUN_A, tmp_path / "results")

    status = graph.publish(state)

    assert status == APPROVED, (
        f"run A publishing its own index should be APPROVED, got {status!r} "
        f"({state.get('publication_reason')!r})"
    )
    assert state.get("publication_status") == APPROVED
    assert state.get("final_rating") == BUY, "an approved run carries the official rating"


@pytest.mark.unit
def test_foreign_index_from_run_a_is_blocked_in_run_b(monkeypatch, tmp_path):
    """Negative: the same candidate citing run A's index must not publish as run B.

    Expected after the fix: BLOCKED / INSUFFICIENT_EVIDENCE, no official rating and
    no decision body. On the starting revision ``publish`` ignores ``course_run``,
    so it returns APPROVED and this test fails on the first assertion.
    """
    graph = _make_graph(monkeypatch, tmp_path)
    state = _state_for_current_run(RUN_B, tmp_path / "results")
    index_run_id = state["evidence_index"]["run_id"]
    assert index_run_id == RUN_A
    assert state["course_run"]["run_id"] == RUN_B
    # The records themselves also name run A: ownership is read from the record,
    # not from the index's metadata key.
    for record in state["evidence_index"]["evidence"].values():
        assert record["run_id"] == RUN_A
    for record in state["argument_index"].values():
        assert record["run_id"] == RUN_A

    status = graph.publish(state)

    assert status == BLOCKED, (
        f"run {RUN_B} cited an evidence index belonging to {index_run_id}, "
        f"but publish() returned {status!r} (reason {state.get('publication_reason')!r})"
    )
    assert state.get("publication_reason") == INSUFFICIENT_EVIDENCE, (
        "a foreign-run reference is insufficient evidence, got "
        f"{state.get('publication_reason')!r}"
    )
    assert state.get("publication_status") == BLOCKED
    assert state.get("final_rating") in (None, ""), (
        f"a blocked run must carry no official rating, got {state.get('final_rating')!r}"
    )
    assert state.get("final_trade_decision") in (None, ""), (
        "a blocked run must carry no decision body, got "
        f"{state.get('final_trade_decision')!r}"
    )
