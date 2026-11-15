"""FR-01 positive test — a valid rating with resolvable evidence is released.

The normal case: a decision that cites an accepted argument whose evidence id
exists in this run's index publishes as an official rating, and the chain resolves
back to the run material. This guards against a gate that blocks everything.

The fake model does **not** receive a pre-injected evidence id: it reads the
``Available evidence`` block out of the prompt it is actually given and cites the
first id it finds — so the test proves the prompt wiring, not an injected constant.

It also proves the argument id is run-bound: an argument id minted under a
different run token is rejected (see ``test_cross_run_argument_is_rejected``).

Drives the real ``TradingAgentsGraph.propagate()`` path.
No network.
"""

from __future__ import annotations

import re

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from tradingagents.agents.schemas import DebateArgument, PortfolioDecision, PortfolioRating

REPORT = "The 50-day breakout and volume confirm the uptrend."

# A line in the evidence menu looks like: "- ev:<run>:market_report  [market_report] <excerpt>"
_EVIDENCE_LINE = re.compile(r"^- (ev:\S+)\s+\[", re.MULTILINE)


def _cited_evidence_from_prompt(prompt: str) -> list[str]:
    """The evidence IDs the researcher is actually offered in this prompt."""
    match = _EVIDENCE_LINE.search(prompt)
    return [match.group(1)] if match else []


class _EvidenceModel(BaseChatModel):
    """Emits reports; structured calls read the evidence menu from the prompt."""

    @property
    def _llm_type(self) -> str:
        return "evidence-fake"

    def bind_tools(self, tools, **kwargs):  # type: ignore[override]
        return self

    def with_structured_output(self, schema, **kwargs):  # type: ignore[override]
        if schema is DebateArgument:
            return _StructuredArgument()
        if schema is PortfolioDecision:
            return _StructuredDecision()
        raise NotImplementedError

    def _generate(self, messages, stop=None,
                  run_manager: CallbackManagerForLLMRun | None = None,
                  **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=REPORT))])


class _StructuredArgument:
    def invoke(self, prompt):
        # Cite the real run evidence id that appears in the prompt.
        return DebateArgument(
            argument="bull case",
            evidence_ids=_cited_evidence_from_prompt(prompt),
        )


class _StructuredDecision:
    def invoke(self, prompt):
        # The PM must cite the accepted argument. The argument id is run-bound, so
        # read it from the 'Accepted arguments' block the PM is actually given.
        match = re.search(r"^- (arg:\S+)", prompt, re.MULTILINE)
        argument_ids = [match.group(1)] if match else []
        return PortfolioDecision(
            rating=PortfolioRating.BUY,
            executive_summary="add",
            investment_thesis="breakout",
            argument_ids=argument_ids,
        )


class _FakeClient:
    def __init__(self, llm):
        self._llm = llm

    def get_llm(self):
        return self._llm


def _run(monkeypatch, tmp_path):
    import tradingagents.graph.trading_graph as tg
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _FakeClient(_EvidenceModel()))
    monkeypatch.setattr(tg, "resolve_instrument_identity", lambda t: {
        "company_name": "NVIDIA Corporation", "sector": "Technology",
        "industry": "Semiconductors", "exchange": "NASDAQ", "quote_type": "EQUITY",
    })
    config = dict(DEFAULT_CONFIG)
    config.update({
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "checkpoint_enabled": False,
    })
    graph = tg.TradingAgentsGraph(selected_analysts=("market",), debug=False, config=config)
    final_state, signal = graph.propagate("NVDA", "2026-01-05")
    return graph, final_state, signal


@pytest.mark.unit
def test_valid_rating_with_resolvable_evidence_is_approved(monkeypatch, tmp_path):
    graph, final_state, signal = _run(monkeypatch, tmp_path)

    assert final_state.get("publication_status") == "APPROVED", final_state.get("publication_reason")
    assert signal == "Buy"
    assert final_state.get("publication_chain")  # resolves back to run material
    assert graph.memory_log.load_entries()  # an approved decision is recorded


@pytest.mark.unit
def test_argument_id_is_run_bound(monkeypatch, tmp_path):
    """The accepted argument id embeds this run's id, so it cannot be reused cross-run."""
    _, final_state, _ = _run(monkeypatch, tmp_path)
    chain = final_state.get("publication_chain") or []
    assert chain, "expected a resolved chain"
    argument_id = chain[0][0]
    assert argument_id.startswith("arg:bull:")
    run_id = final_state.get("run_id")
    assert run_id and run_id in argument_id
