"""FR-01 / INV-01 — reference aliases at the real Bull, Bear and Portfolio Manager nodes.

The defect this file pins down: the prompts offer long, run-bound IDs
(``ev:<run>:market_snapshot:<call>``, ``arg:bull:<run>:<n>``) that a model tends
to shorten or truncate. The approved fix is a *program-side adapter*: each
individual researcher invocation offers ``E1``, ``E2`` ... aliases for the
current evidence menu, and each Portfolio Manager invocation offers ``A1``,
``A2`` ... aliases for the accepted arguments. The program converts those local
aliases to the full IDs **before** the unchanged ``validate_argument`` /
``evaluate_publication`` run. The original 17 cases touch the real node factories
and graph, so the pre-change red demonstrates actual rejection of E1/A1.
Three added helper-level cases cover opaque-ID collisions and later selections;
those cases review the generated adapter and are separate from baseline evidence.

Safety properties asserted here (C1 v1.0, INV-01):

- The full canonical IDs still work, and the full-ID menu lines are still offered.
- An alias only ever resolves to *this invocation's* record: an unknown alias,
  a shortened ``ev:``/``arg:`` reference, or a mixed list is refused (never
  silently filtered); a canonical ID belonging to another run never resolves.
- The same ``E1`` in two separate runs resolves to each run's own full record.
- The alias table is local to one invocation; a second invocation of the same
  node gets its own table.
- An empty evidence index offers no usable alias.
- Unknown references are reported through a logger warning that names the actor
  and the rejected reference, but not the raw claim text.

All runs use a pinned, synthetic OHLCV frame served in place of the vendor
download and a fake structured model; there is no network and no live call.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from tradingagents.agents.schemas import DebateArgument, PortfolioDecision, PortfolioRating

TRADE_DATE = "2026-01-05"

# A line in the evidence menu looks like: "- ev:<run>:market_snapshot:<call>  [market_snapshot] <excerpt>"
_EVIDENCE_LINE = re.compile(r"^- (ev:\S+)\s+\[", re.MULTILINE)
# An alias offered for an evidence line, in either accepted shape: a bare "E1" beside
# the full id on the same line, or an "= E1"-style tag appended to the line.
_ALIAS_ON_EVIDENCE_LINE = re.compile(r"^(?:- )?\s*(E\d+)\s*$|=\s*(E\d+)\s*$", re.MULTILINE)
_ACCEPTED_BLOCK = re.compile(
    r"\*\*Accepted arguments\*\*.*?\n((?:- .*\n)*)", re.MULTILINE
)
_ACCEPTED_LINE = re.compile(r"^- (\S+)(?:\s+\([^\n]*)?\)?\s*$", re.MULTILINE)
_ARG_ALIAS_LINE = re.compile(r"^(?:- )?\s*(A\d+)\s*$|=\s*(A\d+)\b", re.MULTILINE)

_SNAPSHOT_TOOL = "get_verified_market_snapshot"


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
    """Serve a fixed OHLCV frame in place of the vendor download."""
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


def _evidence_ids_in_prompt(prompt: str) -> list[str]:
    """The full canonical evidence IDs the researcher is actually offered."""
    return [match.group(1) for match in _EVIDENCE_LINE.finditer(prompt)]


def _evidence_aliases_in_prompt(prompt: str) -> list[str]:
    """The evidence aliases (E1, E2 ...) actually offered in this prompt."""
    found = [
        (m.start(), m.group(1) or m.group(2))
        for m in _ALIAS_ON_EVIDENCE_LINE.finditer(prompt)
    ]
    return [alias for _pos, alias in sorted(found)]


class _ScriptedModel(BaseChatModel):
    """Emits fixed reports; the market analyst first calls the snapshot tool.

    ``researcher_reply`` and ``pm_reply`` are ``(prompt_text) -> list[str]``:
    they receive the prompt the node really built and return the references the
    fake model would emit. That proves the prompt wiring, not an injected value.
    """

    researcher_reply: Any = None
    pm_reply: Any = None
    researcher_claim: str = "bull case"
    snapshot_calls: int = 0
    structured_calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "reference-alias-fake"

    def bind_tools(self, tools, **kwargs):  # type: ignore[override]
        return self

    def with_structured_output(self, schema, **kwargs):  # type: ignore[override]
        if schema is DebateArgument:
            return _StructuredArgument(self)
        if schema is PortfolioDecision:
            return _StructuredDecision(self)
        raise NotImplementedError

    def _generate(self, messages, stop=None,
                  run_manager: CallbackManagerForLLMRun | None = None,
                  **kwargs) -> ChatResult:
        text = _prompt_text(messages).lower()
        is_analyst = "you are a trading assistant" in text or "ohlcv" in text
        if is_analyst and self.snapshot_calls == 0:
            self.snapshot_calls += 1
            return ChatResult(generations=[ChatGeneration(message=AIMessage(
                content="",
                tool_calls=[{
                    "name": _SNAPSHOT_TOOL,
                    "args": {"curr_date": TRADE_DATE, "look_back_days": 7},
                    "id": "call-1",
                }],
            ))])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(
            content="The 50-day breakout and volume confirm the uptrend."
        ))])


class _StructuredArgument:
    def __init__(self, model: _ScriptedModel):
        self._model = model

    def invoke(self, prompt):
        self._model.structured_calls += 1
        reply = self._model.researcher_reply
        ids = reply(_prompt_text(prompt)) if callable(reply) else list(reply or ())
        return DebateArgument(argument=self._model.researcher_claim, evidence_ids=list(ids))


class _StructuredDecision:
    def __init__(self, model: _ScriptedModel):
        self._model = model

    def invoke(self, prompt):
        self._model.structured_calls += 1
        reply = self._model.pm_reply
        ids = reply(_prompt_text(prompt)) if callable(reply) else list(reply or ())
        return PortfolioDecision(
            rating=PortfolioRating.BUY,
            executive_summary="add",
            investment_thesis="breakout",
            argument_ids=list(ids),
        )


class _FakeClient:
    def __init__(self, llm):
        self._llm = llm

    def get_llm(self):
        return self._llm


def _cite_evidence_aliases(text: str) -> list[str]:
    aliases = _evidence_aliases_in_prompt(text)
    return [aliases[0]] if aliases else ["E1"]


def _cite_argument_aliases(text: str) -> list[str]:
    aliases = [m.group(1) or m.group(2) for m in _ARG_ALIAS_LINE.finditer(text)]
    return [aliases[0]] if aliases else ["A1"]


def _cite_canonical_evidence(text: str) -> list[str]:
    ids = _evidence_ids_in_prompt(text)
    assert ids, "the researcher prompt offered no canonical evidence ID"
    return [ids[0]]


def _cite_canonical_argument(text: str) -> list[str]:
    block = _ACCEPTED_BLOCK.search(text)
    assert block, "the Portfolio Manager prompt listed no accepted arguments"
    ids = [m.group(1) for m in _ACCEPTED_LINE.finditer(block.group(1))]
    assert ids, "the accepted-arguments block listed no IDs"
    return [ids[0]]


def _run(monkeypatch, tmp_path, *, researcher_reply=_cite_evidence_aliases,
         pm_reply=_cite_argument_aliases, tag=""):
    import tradingagents.graph.trading_graph as tg
    from tradingagents.default_config import DEFAULT_CONFIG

    _pin_snapshot(monkeypatch)
    model = _ScriptedModel(researcher_reply=researcher_reply, pm_reply=pm_reply)
    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _FakeClient(model))
    monkeypatch.setattr(tg, "resolve_instrument_identity", lambda t: {
        "company_name": "NVIDIA Corporation", "sector": "Technology",
        "industry": "Semiconductors", "exchange": "NASDAQ", "quote_type": "EQUITY",
    })
    config = dict(DEFAULT_CONFIG)
    config.update({
        "data_cache_dir": str(tmp_path / ("cache" + tag)),
        "results_dir": str(tmp_path / ("results" + tag)),
        "memory_log_path": str(tmp_path / ("memory" + tag + ".md")),
        "checkpoint_enabled": False,
    })
    graph = tg.TradingAgentsGraph(selected_analysts=("market",), debug=False, config=config)
    final_state, signal = graph.propagate("NVDA", TRADE_DATE)
    assert model.snapshot_calls >= 1, (
        "the market analyst never called the snapshot tool, so the run has no "
        "retained material and cannot approve"
    )
    return graph, final_state, signal, model


def _retained_evidence(state: dict) -> dict[str, dict]:
    evidence = (state.get("evidence_index") or {}).get("evidence") or {}
    assert isinstance(evidence, dict) and evidence, (
        f"the run must index retained evidence as a mapping: {type(evidence).__name__}"
    )
    return evidence


# ---------------------------------------------------------------------------
# The real graph: aliases resolve to canonical IDs everywhere downstream
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_alias_citations_publish_with_canonical_ids(monkeypatch, tmp_path):
    """A model that cites only E1/A1 approves with full canonical IDs in the chain."""
    graph, state, signal, _model = _run(monkeypatch, tmp_path)

    assert state.get("publication_status") == "APPROVED", state.get("publication_reason")
    assert signal == "Buy"

    evidence = _retained_evidence(state)
    chain = state.get("publication_chain") or []
    assert chain, "expected the approved chain to resolve back to run material"
    for argument_id, evidence_id, _source in chain:
        assert argument_id in state["argument_index"], f"chain carries an alias, not a canonical id: {argument_id}"
        assert evidence_id in evidence, f"chain carries an alias, not a canonical id: {evidence_id}"

    # Retained content still resolves for every evidence id the chain used.
    from tradingagents.agents.evidence_collection import resolve_content_ref

    for evidence_id in state["publication_result"]["evidence_ids"]:
        record = evidence[evidence_id]
        content_ref = record.get("content_ref") or ""
        assert content_ref, f"indexed evidence {evidence_id} names no retained material"
        assert resolve_content_ref(content_ref, graph.config["results_dir"], record), (
            f"the indexed material does not resolve: {content_ref}"
        )
    assert graph.memory_log.load_entries()  # an approved decision is recorded


@pytest.mark.unit
def test_canonical_only_fake_model_remains_accepted(monkeypatch, tmp_path):
    """The full canonical references keep working; the full-ID menu lines remain."""
    _graph, state, signal, _model = _run(
        monkeypatch, tmp_path,
        researcher_reply=_cite_canonical_evidence,
        pm_reply=_cite_canonical_argument,
    )

    assert state.get("publication_status") == "APPROVED", state.get("publication_reason")
    assert signal == "Buy"
    evidence = _retained_evidence(state)
    argument_index = state.get("argument_index") or {}
    for argument_id, evidence_id, _source in state.get("publication_chain") or []:
        assert argument_id in argument_index
        assert evidence_id in evidence


@pytest.mark.unit
@pytest.mark.parametrize(
    "model_reply",
    [
        pytest.param(lambda _text: ["E99"], id="unknown-alias"),
        pytest.param(lambda _text: ["ev:"], id="shortened-ev-ref"),
        pytest.param(lambda _text: ["E1", "E99"], id="mixed-alias-and-unknown"),
    ],
)
def test_unresolvable_researcher_reference_is_blocked(monkeypatch, tmp_path, model_reply):
    """An unknown or shortened evidence reference is refused, never filtered out.

    ``E1`` alone would resolve, so the mixed case proves a partly-resolvable
    citation does not become a partial acceptance.
    """
    _graph, state, signal, _model = _run(monkeypatch, tmp_path, researcher_reply=model_reply)

    assert state.get("publication_status") == "BLOCKED"
    assert state.get("publication_reason") == "INSUFFICIENT_EVIDENCE"
    assert signal == "REVIEW"
    assert not state.get("argument_index"), (
        "a refused evidence reference must not mint an accepted argument"
    )
    assert state.get("final_rating") == ""


@pytest.mark.unit
@pytest.mark.parametrize(
    "target",
    [pytest.param("bear", id="bear"), pytest.param("bull", id="bull")],
)
def test_researcher_alias_canonicalizes_to_its_own_full_record(monkeypatch, tmp_path, target):
    """Bull and Bear each turn E1 into the full ID of *their* invocation's record.

    The node is driven directly on a real run state, so the exact invocation and
    its alias table are the ones under test. Both the accepted branch (the record
    lands in ``argument_index`` keyed by the full ID) and the pending branch
    (``pending_argument`` carries full IDs in both states) are checked.
    """
    import tradingagents.graph.trading_graph as tg

    _pin_snapshot(monkeypatch)
    model = _ScriptedModel(researcher_reply=_cite_evidence_aliases, pm_reply=_cite_argument_aliases)
    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _FakeClient(model))
    monkeypatch.setattr(tg, "resolve_instrument_identity", lambda t: {})
    from tradingagents.default_config import DEFAULT_CONFIG

    config = dict(DEFAULT_CONFIG)
    config.update({
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "checkpoint_enabled": False,
    })
    graph = tg.TradingAgentsGraph(selected_analysts=("market",), debug=False, config=config)

    from tradingagents.agents import create_bear_researcher, create_bull_researcher
    from tradingagents.dataflows.config import run_config

    factory = create_bear_researcher if target == "bear" else create_bull_researcher
    speaker = "Bear Analyst" if target == "bear" else "Bull Analyst"

    with run_config(config):
        state = graph.create_run_state("NVDA", TRADE_DATE)
        # The analysts' own step: index the retained snapshot before the debate.
        from tradingagents.agents.evidence_collection import record_market_snapshot
        from tradingagents.agents.tools import get_verified_market_snapshot
        from tradingagents.graph.setup import _index_evidence_node

        args = {"symbol": "NVDA", "curr_date": TRADE_DATE,
                "trade_date": TRADE_DATE, "look_back_days": 7}
        snapshot = get_verified_market_snapshot.invoke(args)
        collected = record_market_snapshot(
            {"id": "call-seed", "name": _SNAPSHOT_TOOL, "args": args},
            snapshot, state, state["course_run"], config["results_dir"],
        )
        assert collected["records"], "the node fixture must retain actual source material"
        state["market_evidence"] = collected["records"]
        state.update(_index_evidence_node(state))
        evidence = _retained_evidence(state)
        offered = sorted(evidence)
        state.update({
            "investment_debate_state": {
                "bull_history": "", "bear_history": "", "history": "",
                "current_response": "", "count": 0,
            },
        })
        # The subgraph's identity comes from the seeded course_run, so an older
        # checkpoint path is not exercised here.
        result = factory(model)(state)
        assert speaker in result["pending_argument"]["speaker"]
        pending = result["pending_argument"]["evidence_ids"]
        accepted = result["argument_index"]
        assert len(accepted) == 1, (
            "the alias must be accepted for this run's real evidence record"
        )
        _full_id, record = next(iter(accepted.items()))
        assert pending == record["evidence_ids"]
        for evidence_id in pending:
            assert evidence_id in evidence
            assert evidence_id != "E1"
        assert offered  # the menu offered a full canonical id too


@pytest.mark.unit
@pytest.mark.parametrize(
    "pm_reply",
    [
        pytest.param(lambda _text: ["A99"], id="unknown-alias"),
        pytest.param(lambda _text: ["arg:"], id="shortened-arg-ref"),
        pytest.param(
            lambda text: _cite_argument_aliases(text) + ["A99"],
            id="mixed-alias-and-unknown",
        ),
    ],
)
def test_pm_alias_is_canonical_before_the_gate(monkeypatch, tmp_path, pm_reply):
    """The PM's A1 becomes the canonical argument ID; unknown refs are refused.

    A known A1 seeds the accepted argument, so the unknown/mixed cases prove the
    *invalid* part is what blocks — not an empty index.
    """
    _graph, state, signal, _model = _run(monkeypatch, tmp_path, pm_reply=pm_reply)

    argument_index = state.get("argument_index") or {}
    assert argument_index, "the researcher's alias citation must have been accepted"
    assert state.get("publication_status") == "BLOCKED"
    assert state.get("publication_reason") == "INSUFFICIENT_EVIDENCE"
    assert signal == "REVIEW"
    assert state.get("final_rating") == ""
    assert state.get("final_trade_decision") == ""
    assert not state.get("publication_result") or not state["publication_result"]["rating"]


@pytest.mark.unit
def test_pm_alias_resolves_to_canonical_candidate_refs(monkeypatch, tmp_path):
    """The PM citing A1 reaches the gate as the full accepted argument ID."""
    import tradingagents.graph.trading_graph as tg
    from tradingagents.agents import create_portfolio_manager
    from tradingagents.dataflows.config import run_config
    from tradingagents.default_config import DEFAULT_CONFIG

    _pin_snapshot(monkeypatch)
    model = _ScriptedModel(researcher_reply=_cite_evidence_aliases, pm_reply=_cite_argument_aliases)
    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _FakeClient(model))
    monkeypatch.setattr(tg, "resolve_instrument_identity", lambda t: {})
    config = dict(DEFAULT_CONFIG)
    config.update({
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "checkpoint_enabled": False,
    })
    graph = tg.TradingAgentsGraph(selected_analysts=("market",), debug=False, config=config)

    with run_config(config):
        state = graph.create_run_state("NVDA", TRADE_DATE)
        argument_index = {
            "arg:bull:<run>:1": {
                "contract_version": "1.0",
                "run_id": state["course_run"]["run_id"],
                "ticker": "NVDA", "as_of_date": TRADE_DATE,
                "argument_id": "arg:bull:<run>:1", "claim": "bull case",
                "speaker": "Bull Analyst", "evidence_ids": [],
            },
        }
        state.update({
            "argument_index": argument_index,
            "accepted_arguments": [
                {"argument_id": "arg:bull:<run>:1", "speaker": "Bull Analyst",
                 "evidence_ids": []},
            ],
            "investment_plan": "", "trader_investment_plan": "",
        })
        result = create_portfolio_manager(model)(state)

    assert result["candidate_argument_ids"] == ["arg:bull:<run>:1"]
    assert "A1" not in result["candidate_argument_ids"]


@pytest.mark.unit
def test_same_alias_in_two_runs_resolves_to_each_runs_own_record(monkeypatch, tmp_path):
    """``E1`` is invocation-local: the same alias names each run's own full record."""
    graph_a, state_a, signal_a, _ = _run(monkeypatch, tmp_path, tag="a")
    graph_b, state_b, signal_b, _ = _run(monkeypatch, tmp_path, tag="b")

    assert signal_a == signal_b == "Buy"
    evidence_a = _retained_evidence(state_a)
    evidence_b = _retained_evidence(state_b)
    chain_a = state_a["publication_chain"]
    chain_b = state_b["publication_chain"]
    assert chain_a and chain_b
    ids_a = {link[1] for link in chain_a}
    ids_b = {link[1] for link in chain_b}
    assert ids_a <= set(evidence_a)
    assert ids_b <= set(evidence_b)
    assert ids_a.isdisjoint(ids_b), "E1 resolved to a record from the other run"


@pytest.mark.unit
def test_current_run_does_not_resolve_foreign_canonical_ids(monkeypatch, tmp_path):
    """A canonical ID from another run never resolves against this run's index."""
    from tradingagents.graph.publication_gate import (
        BLOCKED,
        INSUFFICIENT_EVIDENCE,
        evaluate_publication,
    )

    graph, state, signal, _model = _run(monkeypatch, tmp_path)
    assert signal == "Buy"

    run = state["course_run"]
    argument_id, evidence_id, _source = state["publication_chain"][0]
    foreign_run = {**run, "run_id": "run-foreign"}
    foreign_argument = {
        **state["argument_index"][argument_id],
        "run_id": "run-foreign",
        "argument_id": "arg:bull:run-foreign:1",
    }
    foreign = evaluate_publication(
        {"rating": "Buy", "argument_ids": [foreign_argument["argument_id"]]},
        {foreign_argument["argument_id"]: foreign_argument},
        state["evidence_index"],
        foreign_run,
        results_dir=graph.config["results_dir"],
    )
    assert foreign.publication_status == BLOCKED
    assert INSUFFICIENT_EVIDENCE in foreign.reason_codes

    # The local canonical reference still approves, so the foreign block is not a
    # blanket refusal.
    local = evaluate_publication(
        {"rating": "Buy", "argument_ids": [argument_id]},
        state["argument_index"],
        state["evidence_index"],
        run,
        results_dir=graph.config["results_dir"],
    )
    assert local.approved
    assert evidence_id in local.evidence_ids


@pytest.mark.unit
def test_empty_evidence_offers_no_usable_alias(monkeypatch, tmp_path):
    """With no retained evidence, no alias can support approval."""
    import tradingagents.graph.trading_graph as tg
    from tradingagents.agents import create_bull_researcher
    from tradingagents.dataflows.config import run_config
    from tradingagents.default_config import DEFAULT_CONFIG

    captured = {}

    def cite_first_alias(text):
        aliases = _evidence_aliases_in_prompt(text)
        captured["aliases"] = aliases
        return [aliases[0]] if aliases else []

    _pin_snapshot(monkeypatch)
    model = _ScriptedModel(researcher_reply=cite_first_alias, pm_reply=_cite_argument_aliases)
    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _FakeClient(model))
    monkeypatch.setattr(tg, "resolve_instrument_identity", lambda t: {})
    config = dict(DEFAULT_CONFIG)
    config.update({
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "checkpoint_enabled": False,
    })
    graph = tg.TradingAgentsGraph(selected_analysts=("market",), debug=False, config=config)

    with run_config(config):
        state = graph.create_run_state("NVDA", TRADE_DATE)
        state.update({
            "evidence_index": {"run_id": state["course_run"]["run_id"], "evidence": {}},
            "investment_debate_state": {
                "bull_history": "", "bear_history": "", "history": "",
                "current_response": "", "count": 0,
            },
        })
        result = create_bull_researcher(model)(state)

    assert not captured.get("aliases"), (
        f"an empty index must not offer a usable alias: {captured.get('aliases')}"
    )
    assert result["argument_index"] == {}


@pytest.mark.unit
def test_unknown_reference_warns_with_actor_and_reference(monkeypatch, tmp_path, caplog):
    """Rejected references are logged with actor and reference, not the claim text."""
    secret_claim = "SECRET-CLAIM-TEXT-SHOULD-NOT-BE-LOGGED"

    def cite_unknown(_text):
        return ["E99"]

    _pin_snapshot(monkeypatch)
    model = _ScriptedModel(researcher_reply=cite_unknown, pm_reply=_cite_argument_aliases,
                           researcher_claim=secret_claim)
    import tradingagents.graph.trading_graph as tg
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _FakeClient(model))
    monkeypatch.setattr(tg, "resolve_instrument_identity", lambda t: {})
    config = dict(DEFAULT_CONFIG)
    config.update({
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "checkpoint_enabled": False,
    })
    graph = tg.TradingAgentsGraph(selected_analysts=("market",), debug=False, config=config)

    with caplog.at_level(logging.WARNING):
        _state, signal = graph.propagate("NVDA", TRADE_DATE)

    assert signal == "REVIEW"
    warnings = "\n".join(
        record.getMessage() for record in caplog.records
        if record.levelno >= logging.WARNING
    )
    assert "E99" in warnings, f"the invalid reference must be named: {warnings!r}"
    assert re.search(r"bull|bear|researcher", warnings, re.IGNORECASE), (
        f"the diagnostic must name the actor: {warnings!r}"
    )
    assert secret_claim not in warnings, "raw claim text must not be logged"


@pytest.mark.unit
def test_evidence_menus_are_stable_across_invocations(monkeypatch, tmp_path):
    """The same index yields the same alias menu on repeated invocations.

    Each invocation builds its table from that invocation's own index, so two
    invocations over the same records offer the same aliases in the same order,
    while a different index yields a different menu.
    """
    import tradingagents.graph.trading_graph as tg
    from tradingagents.agents import create_bull_researcher
    from tradingagents.dataflows.config import run_config
    from tradingagents.default_config import DEFAULT_CONFIG

    menus = []

    def record_menu(text):
        menus.append(tuple(_evidence_aliases_in_prompt(text)))
        return _cite_evidence_aliases(text)

    _pin_snapshot(monkeypatch)
    model = _ScriptedModel(researcher_reply=record_menu, pm_reply=_cite_argument_aliases)
    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _FakeClient(model))
    monkeypatch.setattr(tg, "resolve_instrument_identity", lambda t: {})
    config = dict(DEFAULT_CONFIG)
    config.update({
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "checkpoint_enabled": False,
    })
    graph = tg.TradingAgentsGraph(selected_analysts=("market",), debug=False, config=config)

    with run_config(config):
        state = graph.create_run_state("NVDA", TRADE_DATE)
        from tradingagents.agents.evidence_collection import record_market_snapshot
        from tradingagents.agents.tools import get_verified_market_snapshot
        from tradingagents.graph.setup import _index_evidence_node

        args = {"symbol": "NVDA", "curr_date": TRADE_DATE,
                "trade_date": TRADE_DATE, "look_back_days": 7}
        snapshot = get_verified_market_snapshot.invoke(args)
        collected = record_market_snapshot(
            {"id": "call-seed", "name": _SNAPSHOT_TOOL, "args": args},
            snapshot, state, state["course_run"], config["results_dir"],
        )
        assert collected["records"], "the node fixture must retain actual source material"
        state["market_evidence"] = collected["records"]
        state.update(_index_evidence_node(state))
        state.update({
            "investment_debate_state": {
                "bull_history": "", "bear_history": "", "history": "",
                "current_response": "", "count": 0,
            },
        })
        node = create_bull_researcher(model)
        node(state)
        node(state)

    assert len(menus) == 2
    assert menus[0] and menus[0] == menus[1]
    assert len(set(menus[0])) == len(menus[0]), "aliases must be unique within a menu"


@pytest.mark.unit
def test_alias_adapters_make_no_extra_model_invocation(monkeypatch, tmp_path):
    """Canonicalizing aliases is program work: it sends no additional model request."""
    import tradingagents.graph.trading_graph as tg
    from tradingagents.default_config import DEFAULT_CONFIG

    _pin_snapshot(monkeypatch)
    alias_model = _ScriptedModel(
        researcher_reply=_cite_evidence_aliases, pm_reply=_cite_argument_aliases,
    )
    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _FakeClient(alias_model))
    monkeypatch.setattr(tg, "resolve_instrument_identity", lambda t: {})
    config = dict(DEFAULT_CONFIG)
    config.update({
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "checkpoint_enabled": False,
    })
    graph = tg.TradingAgentsGraph(selected_analysts=("market",), debug=False, config=config)
    _state, signal = graph.propagate("NVDA", TRADE_DATE)
    assert signal == "Buy"
    alias_calls = alias_model.structured_calls
    alias_snapshot_calls = alias_model.snapshot_calls

    canonical_model = _ScriptedModel(
        researcher_reply=_cite_canonical_evidence, pm_reply=_cite_canonical_argument,
    )
    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _FakeClient(canonical_model))
    config2 = dict(config)
    config2.update({
        "data_cache_dir": str(tmp_path / "cache2"),
        "results_dir": str(tmp_path / "results2"),
        "memory_log_path": str(tmp_path / "memory2.md"),
    })
    graph2 = tg.TradingAgentsGraph(selected_analysts=("market",), debug=False, config=config2)
    _state2, signal2 = graph2.propagate("NVDA", TRADE_DATE)
    assert signal2 == "Buy"

    assert alias_snapshot_calls == canonical_model.snapshot_calls
    assert alias_calls == canonical_model.structured_calls, (
        "the alias adapters must not add a structured model invocation"
    )

@pytest.mark.unit
@pytest.mark.parametrize("prefix", ["E", "A"])
def test_alias_names_never_shadow_a_canonical_reference(prefix):
    """FR-01 / C1: opaque canonical IDs retain their exact selection meaning."""
    from tradingagents.graph.publication_gate import _resolve_selections, _select_aliases

    canonical = ["long-reference-first", f"{prefix}1", "long-reference-last"]
    aliases = _select_aliases(canonical, prefix)
    assert set(aliases).isdisjoint(canonical)
    assert _resolve_selections([f"{prefix}1"], aliases, "test actor") == [f"{prefix}1"]
    assert set(aliases.values()) == set(canonical)


@pytest.mark.unit
def test_later_alias_selects_its_own_record_without_first_item_fallback():
    """FR-01: E2 must select the second record, including in a mixed selection."""
    from tradingagents.graph.publication_gate import _resolve_selections, _select_aliases

    aliases = _select_aliases(["ev:first", "ev:second"], "E")
    assert _resolve_selections(["E2", "E99"], aliases, "Bull Analyst") == [
        "ev:second", "E99",
    ]
