"""INV-01 checkpoint resume — a resumed run keeps its id and its chain verifies.

FR-01 / INV-01, requirement 3: a checkpointed run must be resumable **using the
project's own LangGraph checkpointer** (no ``msgpack`` dependency, no disabling the
checkpoint to dodge the problem). The evidence index is plain, serializable state,
so an interrupted run saves and a subsequent invocation on the same ticker+date
resumes it. The resumed run must:

- keep the **same run id** the interrupted run minted (ids are stable across a
  resume), so an argument accepted before the interruption is still resolvable;
- still resolve that argument's evidence, and so a legal decision is approved.

The interruption is real: the fake model raises inside the first risk-debate turn,
*after* the Bull has accepted an argument against the index and the checkpoint has
saved it. The second ``propagate`` call resumes from that checkpoint.
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

_EVIDENCE_LINE = re.compile(r"^- (ev:\S+)\s+\[", re.MULTILINE)
_ARGUMENT_LINE = re.compile(r"^- (arg:\S+)", re.MULTILINE)

# Set once the run has accepted the Bull argument; the next risk-debate turn crashes.
_CRASH_STATE = {"remaining": 0}

_TICKER = "NVDA"
_AS_OF_DATE = "2026-01-05"


def _pin_snapshot(monkeypatch):
    """Serve a fixed OHLCV frame in place of the vendor download.

    The market analyst really calls ``get_verified_market_snapshot``, so the run
    retains material the gate can re-read after the resume. Only ``load_ohlcv`` is
    replaced; the real tool closure, rendering and ``as_of`` clamp still run.
    """
    import pandas as pd

    import tradingagents.dataflows.vendors.yahoo.snapshot as snapshot

    frame = pd.DataFrame(
        [
            {"Date": d, "Open": o, "High": h, "Low": low, "Close": c, "Volume": v}
            for d, o, h, low, c, v in (
                ("2025-12-30", 138.10, 140.20, 137.05, 139.80, 51_200_000),
                ("2025-12-31", 139.80, 142.40, 139.10, 141.95, 49_800_000),
                ("2026-01-02", 141.95, 144.10, 141.20, 143.60, 52_500_000),
                ("2026-01-05", 143.60, 145.30, 142.80, 144.90, 55_100_000),
            )
        ],
        columns=["Date", "Open", "High", "Low", "Close", "Volume"],
    )
    monkeypatch.setattr(snapshot, "load_ohlcv", lambda *a, **k: frame.copy())


class _CrashException(RuntimeError):
    """Raised from the first risk-debate turn to interrupt the run."""


class _CrashThenSucceedModel(BaseChatModel):
    """Crashes during the risk debate once; every later call succeeds."""

    snapshot_calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "crash-then-succeed-fake"

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
        prompt = _prompt_text(messages)
        low = prompt.lower()
        # The market analyst's first turn is a real snapshot tool call, so the run
        # has retained material the resumed gate can re-read.
        is_analyst = "you are a trading assistant" in low or "ohlcv" in low
        if is_analyst and self.snapshot_calls == 0:
            self.snapshot_calls += 1
            return ChatResult(generations=[ChatGeneration(message=AIMessage(
                content="",
                tool_calls=[{
                    "name": "get_verified_market_snapshot",
                    "args": {"curr_date": _AS_OF_DATE, "look_back_days": 7},
                    "id": "call-1",
                }],
            ))])
        # The risk debators run after the Bull/Research Manager/Trader, so a crash
        # here leaves the accepted argument in the saved checkpoint.
        if _CRASH_STATE["remaining"] > 0 and "Neutral Risk Analyst" in prompt:
            _CRASH_STATE["remaining"] -= 1
            raise _CrashException("simulated interruption during the risk debate")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=REPORT))])


def _prompt_text(messages) -> str:
    """The text of a chat prompt, whether passed as a string or a message list."""
    to_messages = getattr(messages, "to_messages", None)
    if callable(to_messages):
        messages = to_messages()
    if isinstance(messages, str):
        return messages
    return " ".join(str(getattr(m, "content", m)) for m in messages)


class _StructuredArgument:
    def invoke(self, prompt):
        text = _prompt_text(prompt)
        match = _EVIDENCE_LINE.search(text)
        return DebateArgument(
            argument="bull case",
            evidence_ids=[match.group(1)] if match else [],
        )


class _StructuredDecision:
    def invoke(self, prompt):
        text = _prompt_text(prompt)
        match = _ARGUMENT_LINE.search(text)
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


def _make_graph(monkeypatch, tmp_path, crashes: int):
    import tradingagents.graph.trading_graph as tg
    from tradingagents.default_config import DEFAULT_CONFIG

    _pin_snapshot(monkeypatch)
    _CRASH_STATE["remaining"] = crashes
    monkeypatch.setattr(tg, "create_tier_client",
                        lambda *a, **k: _FakeClient(_CrashThenSucceedModel()))
    monkeypatch.setattr(tg, "resolve_instrument_identity", lambda t: {
        "company_name": "NVIDIA Corporation", "sector": "Technology",
        "industry": "Semiconductors", "exchange": "NASDAQ", "quote_type": "EQUITY",
    })
    config = dict(DEFAULT_CONFIG)
    config.update({
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        # Checkpointing stays on: the whole point is to resume from it.
        "checkpoint_enabled": True,
    })
    return tg.TradingAgentsGraph(selected_analysts=("market",), debug=False, config=config)


@pytest.mark.unit
def test_resume_after_interruption_keeps_run_id_and_approves(monkeypatch, tmp_path):
    graph = _make_graph(monkeypatch, tmp_path, crashes=1)

    # First attempt: interrupted during the risk debate, after the index and an
    # accepted argument were saved.
    with pytest.raises(_CrashException):
        graph.propagate("NVDA", "2026-01-05")

    # Second attempt resumes (same ticker+date, same graph shape).
    final_state, signal = graph.propagate("NVDA", "2026-01-05")

    assert final_state.get("publication_status") == "APPROVED", final_state.get("publication_reason")
    assert signal == "Buy"
    # The run id survived the interruption and is the one embedded in the argument id.
    assert final_state.get("run_id")
    chain = final_state.get("publication_chain") or []
    assert chain, "expected the resumed run to resolve its chain"
    assert final_state["run_id"] in chain[0][0]

    # Ownership is the record's full identity: the argument accepted before the
    # interruption is still the resumed run's, and its evidence still resolves.
    run_id = final_state["run_id"]
    argument_id = chain[0][0]
    argument = (final_state.get("argument_index") or {}).get(argument_id)
    assert isinstance(argument, dict), (
        "the pre-interruption argument must survive in the authoritative "
        f"argument_index: {sorted(final_state.get('argument_index') or {})}"
    )
    assert argument.get("run_id") == run_id
    assert argument.get("ticker") == _TICKER
    assert argument.get("as_of_date") == _AS_OF_DATE

    evidence = (final_state.get("evidence_index") or {}).get("evidence") or {}
    assert isinstance(evidence, dict) and evidence, (
        f"the resumed run must keep its evidence mapping: {type(evidence).__name__}"
    )
    for record in evidence.values():
        assert record.get("run_id") == run_id
        assert record.get("ticker") == _TICKER
        assert record.get("as_of_date") == _AS_OF_DATE
        assert record.get("content_ref"), (
            "a resumed run's evidence must still name retained material"
        )
    assert chain[0][1] in evidence, (
        f"the resolved evidence is not in the run's index: {chain[0][1]!r}"
    )


@pytest.mark.unit
def test_resume_keeps_the_same_run_id_across_the_interruption(monkeypatch, tmp_path):
    """The run id minted before the crash is the id the resumed run reports."""
    graph = _make_graph(monkeypatch, tmp_path, crashes=1)

    with pytest.raises(_CrashException):
        graph.propagate("NVDA", "2026-01-05")

    # Inspect the checkpointed state directly to read the id it saved.
    tid = graph.begin_checkpoint("NVDA", "2026-01-05")
    try:
        checkpointed_id = graph.graph.get_state(
            {"configurable": {"thread_id": tid}}
        ).values.get("run_id")
    finally:
        graph.end_checkpoint()

    final_state, _ = graph.propagate("NVDA", "2026-01-05")

    assert checkpointed_id, "the interrupted run should have saved a run id"
    assert final_state.get("run_id") == checkpointed_id
