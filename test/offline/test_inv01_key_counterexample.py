"""INV-01 key counterexample — a valid Buy with no valid evidence must not publish.

Requirement: FR-01 / INV-01 (requirements.yaml).
Plan: revision 1, key counterexample test. Approved: <approver>, <time>, <plan version/link>.

This test drives the *real* ``TradingAgentsGraph.propagate()`` entry point with a
fake chat model, so it exercises the baseline's actual publication path — not a
stub. The model produces a decision text that carries a legal ``**Rating**: Buy``
label but cites no evidence at all. FR-01/INV-01 require that such a candidate be
blocked: it must not be returned as an official rating by the Python API, and it
must not be written to decision memory (no entry at all, not even REVIEW).

The two observations are asserted separately and in isolation so a failure at the
first exit does not mask the result at the second. On the unmodified baseline
(0da00bc) neither guard exists, so both assertions are expected to fail because
the Buy leaks — not because a new field or module is missing.

No network. No new project modules imported. No new state fields depended on.
``resolve_instrument_identity`` is patched to a fixed identity so ``propagate()``
never reaches a live quote. The fake model and all fixed samples are inlined.
"""

from __future__ import annotations

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

# --- fixed samples (inlined, not a fixtures directory) -----------------------

# A decision that carries a legal Buy rating but no argument/evidence citation.
# This is exactly the "valid rating, no valid evidence" counterexample.
BUY_NO_EVIDENCE_DECISION = (
    "**Rating**: Buy\n\n"
    "**Executive Summary**: Enter a full position now.\n\n"
    "**Investment Thesis**: The setup looks strong. I am committing to Buy."
)

# Analyst reports are non-empty so the baseline graph produces a full run; they
# are deliberately generic prose and cite no evidence IDs (the baseline has no
# such concept anyway).
ANALYST_REPORT = "Analysis prose for this run. No structured evidence references are present."
RESEARCH_PLAN = "**Recommendation**: Buy\n\n**Rationale**: Bullish.\n\n**Strategic Actions**: Add."
TRADER_PLAN = "FINAL TRANSACTION PROPOSAL: **BUY**"
DEBATER_ARGUMENT = "Analyst: the case is made from the reports above."


class _BuyNoEvidenceModel(BaseChatModel):
    """A fake chat model that always answers BUY_NO_EVIDENCE_DECISION.

    It reports no tool calls (so an analyst's turn ends with its report) and it
    declines structured output (so the Portfolio Manager takes the baseline's
    free-text path — the exact path FR-01 says must not bypass the gate). Using
    the real free-text path keeps this counterexample honest: the leak it exposes
    is the baseline's, not one manufactured by the test.
    """

    @property
    def _llm_type(self) -> str:
        return "buy-no-evidence-fake"

    def bind_tools(self, tools, **kwargs):  # type: ignore[override]
        # Analysts must not loop on tool calls: stay the same model, but every
        # reply reports no tool_calls, so take_turn ends the analyst's turn.
        return self

    def with_structured_output(self, schema, **kwargs):  # type: ignore[override]
        # Force the free-text fallback in bind_structured()/invoke_structured().
        raise NotImplementedError("structured output disabled for counterexample")

    def _generate(
        self,
        messages,
        stop=None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs,
    ) -> ChatResult:
        message = AIMessage(content=BUY_NO_EVIDENCE_DECISION)
        return ChatResult(generations=[ChatGeneration(message=message)])


class _FakeClient:
    """Stand-in for a provider client: ``get_llm()`` returns the fake model."""

    def __init__(self, llm):
        self._llm = llm

    def get_llm(self):
        return self._llm


# Fixed instrument identity so propagate() never reaches a real quote lookup.
FIXED_NVDA_IDENTITY = {
    "company_name": "NVIDIA Corporation",
    "sector": "Technology",
    "industry": "Semiconductors",
    "exchange": "NASDAQ",
    "quote_type": "EQUITY",
}


def _run_through_propagate(monkeypatch, tmp_path):
    """Drive the real propagate() path offline and return (signal, memory_log).

    Two module attributes are patched in the trading_graph namespace so the graph
    builds with the fake model and a fixed instrument identity, touching neither a
    provider nor a live quote:

    - ``create_tier_client`` -> fake model (no provider call).
    - ``resolve_instrument_identity`` -> FIXED_NVDA_IDENTITY (no market lookup).

    The full config is copied from DEFAULT_CONFIG (never mutated) and only the
    local cache/results/memory paths are overridden; checkpointing stays off.
    All on-disk state goes to ``tmp_path``.
    """
    import tradingagents.graph.trading_graph as tg
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _FakeClient(_BuyNoEvidenceModel()))
    monkeypatch.setattr(tg, "resolve_instrument_identity", lambda ticker: dict(FIXED_NVDA_IDENTITY))

    config = dict(DEFAULT_CONFIG)
    config.update({
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "checkpoint_enabled": False,
    })

    graph = tg.TradingAgentsGraph(
        selected_analysts=("market",),
        debug=False,
        config=config,
    )
    _, signal = graph.propagate("NVDA", "2026-01-05")
    return signal, graph.memory_log


@pytest.mark.unit
def test_buy_without_evidence_is_not_returned_as_official_rating(monkeypatch, tmp_path):
    """Exit 1 — Python API: a legal Buy with no valid evidence must not be returned.

    On the baseline, ``run_rating`` echoes the model's ``**Rating**: Buy`` label,
    so ``propagate()`` returns ``"Buy"`` even though nothing is cited. FR-01 says
    that must be blocked, so this assertion is expected to FAIL on 0da00bc because
    the Buy leaks through the API — the precise behavior INV-01 forbids.
    """
    signal, _ = _run_through_propagate(monkeypatch, tmp_path)

    assert signal != "Buy", (
        "API returned Buy for a candidate with no valid evidence; "
        "the publication gate must block it (FR-01/INV-01)."
    )


@pytest.mark.unit
def test_buy_without_evidence_is_not_written_to_decision_memory(monkeypatch, tmp_path):
    """Exit 2 — decision memory: the blocked candidate must not be persisted.

    Asserted separately from the API check so one failure never masks the other.
    On the baseline, ``record_decision`` calls ``store_decision(... run_rating)``
    unconditionally, so a decision entry lands in the memory log for this run.
    INV-01 says a rejected candidate never enters decision memory, so this asserts
    that *no* decision entry was written for this run — a Buy entry, or even a
    REVIEW entry, must both fail the test. Expected to FAIL on 0da00bc.
    """
    _, memory_log = _run_through_propagate(monkeypatch, tmp_path)

    entries = memory_log.load_entries()

    assert entries == [], (
        "A decision was written to memory for a candidate with no valid evidence; "
        "a rejected candidate must write nothing at all, not even REVIEW (INV-01). "
        f"Found: {[(e.get('ticker'), e.get('rating')) for e in entries]}."
    )
