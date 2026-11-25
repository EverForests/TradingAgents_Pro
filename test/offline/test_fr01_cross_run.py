"""INV-01 cross-run isolation — two independent runs cannot cite each other.

FR-01 / INV-01, requirement 3: a run's id is minted fresh per run (not derived from
ticker+date), so two independent runs on the same instrument and date have
different ids. A decision in the second run that cites the first run's ``evidence_id``
or ``argument_id`` must be blocked — the reference does not resolve in the second
run's index.

Part 1 exercises the gate directly (deterministic). Part 2 checks the same at the
real ``propagate()`` level: two runs on the same ticker+date get different run ids.
"""

from __future__ import annotations

import pytest

from tradingagents.graph import publication_gate as gate


def _index_with_accepted(run_id: str, report: str):
    """An index for ``run_id`` with one argument accepted against its evidence."""
    index = gate.build_evidence_index(run_id, {"market_report": report})
    ev = index.evidence_ids[0]
    argument_id = f"arg:bull:{run_id}:1"
    index.accept(gate.ArgumentRecord(argument_id, "Bull Analyst", "x", (ev,)))
    return index, ev, argument_id


@pytest.mark.unit
def test_citing_another_runs_evidence_id_is_blocked():
    run_a, ev_a, arg_a = _index_with_accepted("run-A", "a")
    # Run B is a different run: its index has its own evidence and no accepted argument.
    run_b, _ev_b, _ = _index_with_accepted("run-B", "b")

    # Run B cannot claim run A's evidence, even by trying to build an identical arg.
    assert run_b.accept(gate.ArgumentRecord(
        "arg:bull:run-B:1", "Bull Analyst", "x", (ev_a,),
    )) is False
    outcome = gate.evaluate(gate.index_to_state(run_b), "Buy", (arg_a,))
    assert outcome.status == gate.BLOCKED
    assert outcome.reason == gate.INSUFFICIENT_EVIDENCE


@pytest.mark.unit
def test_citing_another_runs_argument_id_is_blocked():
    _run_a, _ev_a, arg_a = _index_with_accepted("run-A", "a")
    run_b, ev_b, arg_b = _index_with_accepted("run-B", "b")

    # Run B resolves its own chain fine.
    owns = gate.evaluate(gate.index_to_state(run_b), "Buy", (arg_b,))
    assert owns.status == gate.APPROVED

    # But run A's argument id is not in run B's index.
    outcome = gate.evaluate(gate.index_to_state(run_b), "Buy", (arg_a,))
    assert outcome.status == gate.BLOCKED
    assert outcome.reason == gate.INSUFFICIENT_EVIDENCE


@pytest.mark.unit
def test_two_propagate_runs_on_same_ticker_and_date_get_different_ids(monkeypatch, tmp_path):
    """The run id is per-run, so two independent runs of the same ticker+date differ."""
    from langchain_core.callbacks import CallbackManagerForLLMRun
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    import tradingagents.graph.trading_graph as tg
    from tradingagents.default_config import DEFAULT_CONFIG

    class _NoEvidenceModel(BaseChatModel):
        @property
        def _llm_type(self):
            return "no-evidence-fake"

        def bind_tools(self, tools, **kwargs):  # type: ignore[override]
            return self

        def with_structured_output(self, schema, **kwargs):  # type: ignore[override]
            raise NotImplementedError

        def _generate(self, messages, stop=None,
                      run_manager: CallbackManagerForLLMRun | None = None, **kwargs):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="text"))])

    class _FakeClient:
        def __init__(self, llm):
            self._llm = llm

        def get_llm(self):
            return self._llm

    monkeypatch.setattr(tg, "create_tier_client",
                        lambda *a, **k: _FakeClient(_NoEvidenceModel()))
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

    state_a, _ = graph.propagate("NVDA", "2026-01-05")
    state_b, _ = graph.propagate("NVDA", "2026-01-05")

    assert state_a.get("run_id"), "first run should carry a run id"
    assert state_b.get("run_id"), "second run should carry a run id"
    assert state_a["run_id"] != state_b["run_id"]
