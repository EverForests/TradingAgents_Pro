"""INV-01 four-exit test — a blocked Buy leaks nowhere.

FR-01 / INV-01: a candidate rejected by the publication gate must not appear as
an official rating at any sink — Python API return, CLI display, Markdown report,
HTML report — nor be written to decision memory. This test drives the real
``TradingAgentsGraph.propagate()`` entry point (and the report writers) with the
fake no-evidence model, then checks each exit independently.

Expected after implementation: pass. Before implementation there was no gate, so
this is a behaviour test, not the baseline counterexample.
"""

from __future__ import annotations

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from tradingagents.report_html import render_report
from tradingagents.reporting import write_report_tree

BUY_NO_EVIDENCE = "**Rating**: Buy\n\n**Executive Summary**: buy.\n\n**Investment Thesis**: buy."


class _BuyNoEvidenceModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "buy-no-evidence-fake"

    def bind_tools(self, tools, **kwargs):  # type: ignore[override]
        return self

    def with_structured_output(self, schema, **kwargs):  # type: ignore[override]
        raise NotImplementedError("structured output disabled")

    def _generate(self, messages, stop=None,
                  run_manager: CallbackManagerForLLMRun | None = None,
                  **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=BUY_NO_EVIDENCE))])


class _FakeClient:
    def __init__(self, llm):
        self._llm = llm

    def get_llm(self):
        return self._llm


def _run(monkeypatch, tmp_path):
    import tradingagents.graph.trading_graph as tg
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _FakeClient(_BuyNoEvidenceModel()))
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
def test_python_api_return_is_not_buy(monkeypatch, tmp_path):
    _, _, signal = _run(monkeypatch, tmp_path)
    assert signal != "Buy"


@pytest.mark.unit
def test_memory_has_no_entry(monkeypatch, tmp_path):
    graph, _, _ = _run(monkeypatch, tmp_path)
    assert graph.memory_log.load_entries() == []


@pytest.mark.unit
def test_final_state_carries_blocked_status(monkeypatch, tmp_path):
    _, final_state, _ = _run(monkeypatch, tmp_path)
    assert final_state.get("publication_status") == "BLOCKED"
    assert final_state.get("publication_reason") == "INSUFFICIENT_EVIDENCE"
    assert final_state.get("final_trade_decision") == ""
    # Requirement 4: the returned state has no candidate body, rating or ids, and
    # final_rating is empty (REVIEW appears only in the API's second tuple member).
    assert final_state.get("final_rating") == ""
    assert "candidate_decision" not in final_state
    assert "candidate_rating" not in final_state
    assert "candidate_argument_ids" not in final_state


@pytest.mark.unit
def test_markdown_report_shows_blocked_not_buy(monkeypatch, tmp_path):
    _, final_state, _ = _run(monkeypatch, tmp_path)
    path = write_report_tree(final_state, "NVDA", tmp_path / "report", settings=None, html=False)
    text = path.read_text(encoding="utf-8")
    assert "BLOCKED" in text
    assert "Rating: Buy" not in text


@pytest.mark.unit
def test_html_report_shows_blocked_not_buy(monkeypatch, tmp_path):
    _, final_state, _ = _run(monkeypatch, tmp_path)
    html = render_report("NVDA", final_state, None, [])
    assert "BLOCKED" in html
    assert ">Buy<" not in html
