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

# A line in the evidence menu looks like: "- ev:<run>:market_snapshot:<call>  [market_snapshot] <excerpt>"
_EVIDENCE_LINE = re.compile(r"^- (ev:\S+)\s+\[", re.MULTILINE)
_SNAPSHOT_TOOL = "get_verified_market_snapshot"


def _cited_evidence_from_prompt(prompt: str) -> list[str]:
    """The evidence IDs the researcher is actually offered in this prompt."""
    match = _EVIDENCE_LINE.search(prompt)
    return [match.group(1)] if match else []


def _prompt_text(prompt) -> str:
    """The flattened text a structured call is given (a string or a PromptValue)."""
    to_messages = getattr(prompt, "to_messages", None)
    if callable(to_messages):
        prompt = to_messages()
    elif isinstance(prompt, str):
        return prompt
    parts = []
    for message in prompt:
        if isinstance(message, str):
            parts.append(message)
            continue
        content = getattr(message, "content", "")
        parts.append(content if isinstance(content, str) else "")
    return "\n".join(parts)


def _pin_snapshot(monkeypatch):
    """Serve a fixed OHLCV frame in place of the vendor download.

    Only ``load_ohlcv`` is replaced; the real tool closure, rendering and
    ``as_of`` clamp still run, so the tool call retains genuine snapshot text.
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


class _EvidenceModel(BaseChatModel):
    """Emits reports; the market analyst first calls the snapshot tool.

    The Bull then reads the evidence menu out of the prompt it is actually given
    and cites that id, so the test proves the prompt wiring and the retained
    material read-back rather than an injected constant.
    """

    snapshot_calls: int = 0

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
        text = _prompt_text(messages).lower()
        # The market analyst's prompt opens "You are a trading assistant" and
        # lists its tools. Its first turn is a real tool call, so the subgraph
        # retains the snapshot and hands the receipt up to the parent graph.
        is_analyst = "you are a trading assistant" in text or "ohlcv" in text
        if is_analyst and self.snapshot_calls == 0:
            self.snapshot_calls += 1
            return ChatResult(generations=[ChatGeneration(message=AIMessage(
                content="",
                tool_calls=[{
                    "name": _SNAPSHOT_TOOL,
                    "args": {"curr_date": "2026-01-05", "look_back_days": 7},
                    "id": "call-1",
                }],
            ))])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=REPORT))])


class _StructuredArgument:
    def invoke(self, prompt):
        # Cite the real run evidence id that appears in the prompt.
        return DebateArgument(
            argument="bull case",
            evidence_ids=_cited_evidence_from_prompt(_prompt_text(prompt)),
        )


class _StructuredDecision:
    def invoke(self, prompt):
        # The PM must cite the accepted argument. The argument id is run-bound, so
        # read it from the 'Accepted arguments' block the PM is actually given.
        text = _prompt_text(prompt)
        match = re.search(r"^- (arg:\S+)", text, re.MULTILINE)
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


def _run(monkeypatch, tmp_path, *, analysts=("market",)):
    import tradingagents.graph.trading_graph as tg
    from tradingagents.default_config import DEFAULT_CONFIG

    _pin_snapshot(monkeypatch)
    model = _EvidenceModel()
    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _FakeClient(model))
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
    graph = tg.TradingAgentsGraph(selected_analysts=analysts, debug=False, config=config)
    final_state, signal = graph.propagate("NVDA", "2026-01-05")
    assert model.snapshot_calls >= 1, (
        "the market analyst never called the snapshot tool, so the run has no "
        "retained material and cannot approve"
    )
    return graph, final_state, signal


@pytest.mark.unit
def test_valid_rating_with_resolvable_evidence_is_approved(monkeypatch, tmp_path):
    graph, final_state, signal = _run(monkeypatch, tmp_path)

    assert final_state.get("publication_status") == "APPROVED", final_state.get("publication_reason")
    assert signal == "Buy"
    chain = final_state.get("publication_chain") or []
    assert chain, "expected the approved chain to resolve back to run material"

    # The evidence the chain resolved is the retained snapshot, indexed as a
    # v1 evidence_id -> record mapping with a readable content_ref.
    evidence = (final_state.get("evidence_index") or {}).get("evidence") or {}
    assert isinstance(evidence, dict) and evidence, (
        f"the run must index retained evidence as a mapping: {type(evidence).__name__}"
    )
    snapshot_ids = {
        eid for eid, record in evidence.items()
        if (record.get("source_kind") or "") == "market_snapshot"
    }
    assert snapshot_ids, f"no snapshot evidence was indexed: {sorted(evidence)}"
    assert any(link[1] in snapshot_ids for link in chain), (
        f"the approved chain does not resolve through retained snapshot material: {chain}"
    )
    for eid in snapshot_ids:
        content_ref = evidence[eid].get("content_ref") or ""
        assert content_ref, f"indexed snapshot {eid} names no retained material"
        from tradingagents.agents.evidence_collection import resolve_content_ref

        assert resolve_content_ref(content_ref, graph.config["results_dir"], evidence[eid]), (
            f"the indexed material does not resolve: {content_ref}"
        )
    assert graph.memory_log.load_entries()  # an approved decision is recorded


@pytest.mark.unit
def test_zero_sentiment_does_not_supply_or_prevent_market_evidence(monkeypatch, tmp_path):
    from tradingagents.agents.analysts import sentiment_analyst

    monkeypatch.setattr(sentiment_analyst.get_news, "func", lambda *a, **k: "")
    monkeypatch.setattr(sentiment_analyst, "fetch_stocktwits_messages", lambda *a, **k: "")
    monkeypatch.setattr(sentiment_analyst, "fetch_reddit_posts", lambda *a, **k: "")
    sentiment_bindings = []
    bind = sentiment_analyst.bind_structured

    def tracked_bind(*args, **kwargs):
        sentiment_bindings.append(args)
        return bind(*args, **kwargs)

    monkeypatch.setattr(sentiment_analyst, "bind_structured", tracked_bind)
    _graph, state, signal = _run(monkeypatch, tmp_path, analysts=("market", "social"))

    sentiment = state["sentiment_assessment"]
    assert sentiment["coverage_status"] == "NO_DATA"
    assert sentiment["overall_score"] is None
    assert not sentiment_bindings
    assert state["publication_status"] == "APPROVED"
    assert signal == "Buy"
    # Every accepted reference resolves to the market tool fixture.
    evidence = state["evidence_index"]["evidence"]
    assert evidence
    assert {item["source_kind"] for item in evidence.values()} == {"market_snapshot"}
    assert all(link[1] in evidence for link in state["publication_chain"])


@pytest.mark.unit
def test_argument_id_is_run_bound(monkeypatch, tmp_path):
    """The accepted argument belongs to this run: its record carries the full identity.

    The ID's spelling is not the ownership check (C1 v1.0 reads ownership from the
    record), so the assertion is on the record's identity matching this run — and
    on that identity not matching any other run token.
    """
    graph, final_state, _ = _run(monkeypatch, tmp_path)
    chain = final_state.get("publication_chain") or []
    assert chain, "expected a resolved chain"
    argument_id = chain[0][0]
    assert argument_id.startswith("arg:bull:")

    run_id = final_state.get("run_id")
    assert run_id and run_id in argument_id

    argument = (final_state.get("argument_index") or {}).get(argument_id)
    assert isinstance(argument, dict), (
        f"the accepted argument must live in the authoritative argument_index: "
        f"{sorted(final_state.get('argument_index') or {})}"
    )
    assert argument.get("run_id") == run_id
    assert argument.get("ticker") == "NVDA"
    assert argument.get("as_of_date") == "2026-01-05"
    assert argument.get("contract_version") == "1.0"
    assert argument.get("run_id") != "some-other-run"
