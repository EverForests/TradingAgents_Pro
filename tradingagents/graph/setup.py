import logging
from collections import Counter
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import (
    create_aggressive_debator,
    create_bear_researcher,
    create_bull_researcher,
    create_conservative_debator,
    create_fundamentals_analyst,
    create_market_analyst,
    create_neutral_debator,
    create_news_analyst,
    create_portfolio_manager,
    create_research_manager,
    create_sentiment_analyst,
    create_trader,
)
from tradingagents.agents.analysts.turn import WRAP_UP
from tradingagents.agents.state import AgentState

from .analyst_execution import build_analyst_execution_plan
from .conditional_logic import ConditionalLogic

logger = logging.getLogger(__name__)

# The approved default of the per-run request budget (C0 ``request_limit``).
DEFAULT_REQUEST_LIMIT = 40

# A run's execution state before it finishes (C0). Only a normal finish sets
# ``COMPLETED``; anything else reaching the gate is ``RUN_NOT_COMPLETE``.
RUNNING = "RUNNING"

# Every target a shared conditional router can return. Each edge driven by the
# router maps all of them, so a fall-through return (e.g. under prompt/i18n/
# refactor drift in the speaker labels) can never hit a missing path_map entry
# and crash LangGraph mid-run (#1088).
DEBATE_PATH_MAP = {
    "Bull Researcher": "Bull Researcher",
    "Bear Researcher": "Bear Researcher",
    "Research Manager": "Research Manager",
}
RISK_ANALYSIS_PATH_MAP = {
    "Aggressive Analyst": "Aggressive Analyst",
    "Conservative Analyst": "Conservative Analyst",
    "Neutral Analyst": "Neutral Analyst",
    "Portfolio Manager": "Portfolio Manager",
}


def _tools_or_done(state) -> str:
    """Route an analyst's turn: run its tool calls, or finish with its report."""
    return "tools" if state["messages"][-1].tool_calls else END


def _new_run_id() -> str:
    """A fresh identifier minted once per run, unique across runs.

    Not derived from ticker+date: two independent runs on the same instrument and
    day must have different ids so one cannot cite the other's evidence. It is
    generated with ``uuid4`` and stored in the serializable graph state, then
    reused verbatim on resume (see ``_index_evidence_node``), so a resumed run keeps
    the same id.
    """
    import uuid

    return uuid.uuid4().hex


def _run_context(state) -> dict:
    """R8-B §2 / C0: the one complete ``RunContext`` for this run.

    Written once, at the Index Evidence step, from the id minted at the shared run
    entry and reused verbatim on resume. Every field is copied from the run
    itself, never derived from an ID's spelling.

    ``execution_status`` starts at ``RUNNING``: the run has not finished yet, and
    only a normal finish sets ``COMPLETED`` (see ``TradingAgentsGraph.publish``).
    A terminal C0 failure keeps its own code, and a run still ``RUNNING`` when the
    gate judges it is ``RUN_NOT_COMPLETE``.

    ``request_limit`` is the run's positive-integer request budget, defaulting to
    the approved value of 40. A non-positive or non-integer setting is a
    configuration error, not something to silently clamp.
    """
    from tradingagents.default_config import DEFAULT_CONFIG

    # C0/C1: the shared run entry already created the one complete RunContext.
    # Reuse it verbatim — including on resume — so the identity the material was
    # stamped with is the identity the gate judges.
    seeded = state.get("course_run")
    if isinstance(seeded, dict) and seeded.get("run_id"):
        context = dict(seeded)
        context.setdefault("contract_version", "1.0")
        context["ticker"] = context.get("ticker") or state.get("company_of_interest", "")
        context["as_of_date"] = context.get("as_of_date") or _effective_as_of(state)
        context["execution_status"] = context.get("execution_status") or RUNNING
        limit = context.get("request_limit")
        if limit is None:
            limit = DEFAULT_CONFIG.get("request_limit")
        if limit is None:
            limit = DEFAULT_REQUEST_LIMIT
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError(f"request_limit must be a positive integer, got {limit!r}")
        context["request_limit"] = limit
        # A recorded terminal failure outranks the RUNNING default.
        if state.get("execution_status") in ("FAILED", "BUDGET_EXHAUSTED", "CONTEXT_TOO_LARGE"):
            context["execution_status"] = state["execution_status"]
        return context

    run_id = state.get("run_id") or _new_run_id()
    limit = state.get("request_limit")
    if limit is None:
        limit = DEFAULT_CONFIG.get("request_limit")
    if limit is None:
        limit = DEFAULT_REQUEST_LIMIT
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError(f"request_limit must be a positive integer, got {limit!r}")
    return {
        "contract_version": "1.0",
        "run_id": run_id,
        "ticker": state.get("company_of_interest", ""),
        # The effective cutoff is as_of()'s own result, not the requested date.
        "as_of_date": _effective_as_of(state),
        "execution_status": state.get("execution_status") or RUNNING,
        "request_limit": limit,
    }


def _effective_as_of(state) -> str:
    """The run's effective cutoff date: ``as_of()``'s actual result.

    The window checks and the snapshot retention paths use this same date, so a
    record dated by ``as_of()`` is the record the run's identity names.
    """
    from tradingagents.dataflows.date_window import as_of

    return as_of(state.get("trade_date"), state.get("trade_date"))


def _index_evidence_node(state) -> dict:
    """FR-01 / R8-B §4: build this run's authoritative evidence mapping.

    The run id was minted at the shared run entry, so the one complete
    ``course_run`` written here reuses it and a resumed run never mints a new one.

    The evidence index is an **ID -> record mapping built from retained
    material**: the market analyst's verified snapshots, which the subgraph
    retained and handed up as ``market_evidence``. A record carries its full
    identity and a ``content_ref`` naming its retained file, so the gate can
    re-read the material before publishing. Analyst reports are **not** evidence:
    prose alone has no traceable retained source, so indexing it would let a
    candidate publish without any verified data.

    The mapping is keyed by ``evidence_id`` (C1 v1.0), not a list the gate has to
    search. ``"run_id"`` rides alongside as compatibility metadata only; no
    record's ownership is ever read from it.

    ``argument_index`` starts empty and is filled by the researchers as they cite
    validated evidence.
    """
    course_run = _run_context(state)
    run_id = course_run["run_id"]

    evidence: dict[str, dict] = {}

    def add(record) -> None:
        if not isinstance(record, dict):
            return
        if record.get("run_id") != run_id:
            return
        evidence_id = record.get("evidence_id")
        if not evidence_id or evidence_id in evidence:
            return
        evidence[evidence_id] = {**record, "id": evidence_id}

    # Retained snapshot receipts handed up by the market analyst's subgraph.
    for record in state.get("market_evidence") or ():
        add(record)
    # A caller whose tool messages are on the parent state (no subgraph).
    for record in _collect_snapshots(state, course_run):
        add(record)

    return {
        "run_id": run_id,
        "course_run": course_run,
        "evidence_index": {"run_id": run_id, "evidence": evidence},
        "argument_index": {},
        "accepted_arguments": [],
    }


def _collect_snapshots(state, course_run: dict) -> list[dict]:
    """Retain verified snapshots whose calls and results are on the parent state.

    The market analyst runs in a graph of its own and hands its receipts up as
    ``market_evidence`` (see ``collect_snapshot_evidence``); this path serves a
    caller whose tool messages are already on the run state. A run with no such
    call (a report-only run) or one whose material cannot be retained contributes
    nothing, and never an unresolvable reference.
    """
    from tradingagents.agents.evidence_collection import record_market_snapshot

    try:
        from tradingagents.dataflows.config import get_config

        results_dir = get_config().get("results_dir")
    except Exception:  # noqa: BLE001 — collection is optional, never fatal
        results_dir = None
    if not results_dir:
        return []

    calls = [
        call for message in state.get("messages") or ()
        for call in (getattr(message, "tool_calls", None) or ())
        if isinstance(call, dict) and call.get("name") == "get_verified_market_snapshot"
    ]
    by_id = {call.get("id"): call for call in calls}
    results = []
    for message in state.get("messages") or ():
        call_id = getattr(message, "tool_call_id", None)
        if call_id not in by_id or getattr(message, "name", None) != "get_verified_market_snapshot":
            continue
        try:
            collected = record_market_snapshot(
                tool_call=by_id[call_id], tool_response=getattr(message, "content", ""),
                state=state, run=course_run, results_dir=results_dir,
            )
        except Exception:  # noqa: BLE001 — a bad response is not evidence, not a crash
            continue
        results.extend((collected or {}).get("records") or ())
    return results


def _results_dir():
    """The run's results root, where retained material lives (never fatal).

    The gate re-reads each record's retained material from here, so the argument
    validation layer must judge against the same root.
    """
    try:
        from tradingagents.dataflows.config import get_config

        return get_config().get("results_dir")
    except Exception:  # noqa: BLE001 — an absent config means no material to read
        return None


def _pending_run_context(state) -> dict | None:
    """The run's identity as an analyst subgraph sees it, before Index Evidence.

    ``RunContext`` is created once at the shared run entry. An analyst subgraph
    receives that context on its input state, so it reuses it verbatim — the same
    id, ticker, cutoff date and budget the parent will judge. A caller whose state
    carries only a ``run_id`` (an older checkpoint) still gets the same fields
    derived, and a state with no identity at all returns ``None`` so no receipt is
    stamped with an identity the parent does not share.
    """
    seeded = state.get("course_run")
    if isinstance(seeded, dict) and seeded.get("run_id"):
        return dict(seeded)
    run_id = state.get("run_id")
    if not run_id:
        return None
    return {
        "contract_version": "1.0",
        "run_id": run_id,
        "ticker": state.get("company_of_interest", ""),
        "as_of_date": _effective_as_of(state),
        "execution_status": state.get("execution_status") or RUNNING,
        "request_limit": state.get("request_limit") or DEFAULT_REQUEST_LIMIT,
    }


def _analyst_graph(spec, agent, max_tool_rounds: int):
    """One analyst as a graph of its own: the model and its tools, on a private message history.

    It returns its report, so analysts running side by side never write the same
    key, and its tool calls never reach the other analysts' messages. After
    ``max_tool_rounds`` rounds of tool calls it is told to write its report, and
    that turn ends it whatever it answers, so a model that keeps calling tools
    cannot run the graph into its recursion limit (#1420).

    R8-B §4: a successful verified snapshot this analyst actually called is
    retained and returned as ``market_evidence`` — the evidence records the Index
    Evidence step folds into the run's index. The subgraph owns the tool calls and
    their results, so only this graph can hand them on; a run with no call, or one
    whose material cannot be retained, returns no receipts.
    """
    output = TypedDict(
        f"{spec.key.capitalize()}Report", {spec.report_key: str, "market_evidence": list}
    )
    graph = StateGraph(AgentState, output_schema=output)
    graph.add_node("agent", agent)
    graph.add_edge(START, "agent")
    if not spec.tools:
        graph.add_edge("agent", END)
        return graph.compile()

    def calls(messages):
        return [call["name"] for m in messages for call in (getattr(m, "tool_calls", None) or [])]

    def rounds(messages) -> int:
        return sum(1 for m in messages if getattr(m, "tool_calls", None))

    def more_or_wrap_up(state) -> str:
        return "wrap_up" if rounds(state["messages"]) >= max_tool_rounds else "agent"

    def wrap_up(state):
        repeated = ", ".join(f"{name} x{n}" for name, n in Counter(calls(state["messages"])).most_common())
        logger.warning("%s used its %d tool rounds (%s); asking for its report",
                       spec.agent_node, max_tool_rounds, repeated)
        return agent({**state, "messages": [*state["messages"], HumanMessage(WRAP_UP)]})

    def collect(state):
        """Hand this analyst's retained snapshot evidence to the parent graph."""
        return {"market_evidence": collect_snapshot_evidence(state)}

    def done_or_collect(state) -> str:
        """Every way an analyst finishes passes through ``collect`` for the market.

        A run that called the snapshot and then wrote its report ends at the
        analyst node, not at ``wrap_up``, so the receipt must be collected on that
        path too — otherwise a normal run would hand nothing up.
        """
        return "collect" if spec.key == "market" else END

    def tools_or_done_or_collect(state) -> str:
        return "tools" if state["messages"][-1].tool_calls else done_or_collect(state)

    graph.add_node("tools", ToolNode(list(spec.tools)))
    graph.add_node("wrap_up", wrap_up)
    graph.add_node("collect", collect)
    graph.add_conditional_edges(
        "agent", tools_or_done_or_collect,
        ["tools", "collect"] if spec.key == "market" else ["tools", END],
    )
    graph.add_conditional_edges("tools", more_or_wrap_up, ["agent", "wrap_up"])
    if spec.key == "market":
        # The market analyst's closing step: it has seen every tool result, so it
        # is where this run's verified snapshots are retained before END.
        graph.add_edge("wrap_up", "collect")
        graph.add_edge("collect", END)
    else:
        graph.add_edge("wrap_up", END)
    return graph.compile()


def collect_snapshot_evidence(state) -> list[dict]:
    """Retain this analyst's verified-snapshot results and return their records.

    Reads the ``get_verified_market_snapshot`` calls and their paired results from
    the analyst's own ``messages`` — the only place they exist, because the
    subgraph does not pass its message history to the parent. Every record is
    bound to this run's identity; when the analyst runs ahead of the Index
    Evidence step the same id minted at the run entry dates the receipts, so the
    parent's index and the gate agree. A response that is a placeholder or whose
    material cannot be retained yields no record rather than an unresolvable
    reference.
    """
    from tradingagents.agents.evidence_collection import record_market_snapshot

    run = state.get("course_run")
    if not isinstance(run, dict) or not run.get("run_id"):
        # The Index Evidence step mints the RunContext after the analysts converge,
        # so the subgraph builds the same complete context here from the state —
        # with the id the parent will reuse — and the parent folds the receipts in.
        run = _pending_run_context(state)
    if run is None:
        return []
    try:
        from tradingagents.dataflows.config import get_config

        results_dir = get_config().get("results_dir")
    except Exception:  # noqa: BLE001 — collection is optional, never fatal
        return []
    if not results_dir:
        return []

    by_id = {
        call.get("id"): call
        for message in state.get("messages") or ()
        for call in (getattr(message, "tool_calls", None) or ())
        if isinstance(call, dict) and call.get("name") == "get_verified_market_snapshot"
    }
    records: list[dict] = []
    for message in state.get("messages") or ():
        call_id = getattr(message, "tool_call_id", None)
        if call_id not in by_id or getattr(message, "name", None) != "get_verified_market_snapshot":
            continue
        try:
            collected = record_market_snapshot(
                tool_call=by_id[call_id], tool_response=getattr(message, "content", ""),
                state=state, run=run, results_dir=results_dir,
            )
        except Exception:  # noqa: BLE001 — a bad response is not evidence, not a crash
            continue
        records.extend((collected or {}).get("records") or ())
    seen: set[str] = set()
    unique: list[dict] = []
    for record in records:
        evidence_id = record.get("evidence_id")
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        unique.append(record)
    return unique


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        conditional_logic: ConditionalLogic,
        max_tool_rounds: int,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.conditional_logic = conditional_logic
        self.max_tool_rounds = max_tool_rounds

    def setup_graph(
        self, selected_analysts=("market", "social", "news", "fundamentals"), memory_node=None
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "social": Sentiment analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
            memory_node: Node that settles past decisions and returns the run's
                ``past_context``. It runs alongside the analysts.
        """
        plan = build_analyst_execution_plan(selected_analysts)

        analyst_factories = {
            "market": lambda: create_market_analyst(self.quick_thinking_llm),
            "social": lambda: create_sentiment_analyst(self.quick_thinking_llm),
            "news": lambda: create_news_analyst(self.quick_thinking_llm),
            "fundamentals": lambda: create_fundamentals_analyst(self.quick_thinking_llm),
        }

        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)
        research_manager_node = create_research_manager(self.deep_thinking_llm)
        trader_node = create_trader(self.quick_thinking_llm)

        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm)

        workflow = StateGraph(AgentState)

        for spec in plan.specs:
            workflow.add_node(spec.agent_node,
                              _analyst_graph(spec, analyst_factories[spec.key](), self.max_tool_rounds))

        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        # The analysts work at the same time; the research debate starts once
        # every one of them has filed its report. The memory log settles past
        # decisions alongside them: only the Portfolio Manager reads its lessons.
        first_steps = [spec.agent_node for spec in plan.specs]
        if memory_node is not None:
            workflow.add_node("Memory Log", memory_node)
            first_steps.append("Memory Log")

        # FR-01: index this run's evidence after the analysts converge and
        # before the first Bull turn, so every cited evidence id exists in the
        # run. The index is stored on the state for the researchers to validate
        # against and for the publication gate to verify.
        workflow.add_node("Index Evidence", _index_evidence_node)
        for node in first_steps:
            workflow.add_edge(START, node)
        workflow.add_edge(first_steps, "Index Evidence")
        workflow.add_edge("Index Evidence", "Bull Researcher")

        # Both research-debate edges share the complete DEBATE_PATH_MAP (#1088).
        for debate_node in ("Bull Researcher", "Bear Researcher"):
            workflow.add_conditional_edges(
                debate_node,
                self.conditional_logic.should_continue_debate,
                DEBATE_PATH_MAP,
            )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        # All three risk edges share the complete RISK_ANALYSIS_PATH_MAP (#1088).
        for risk_node in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"):
            workflow.add_conditional_edges(
                risk_node,
                self.conditional_logic.should_continue_risk_analysis,
                RISK_ANALYSIS_PATH_MAP,
            )

        workflow.add_edge("Portfolio Manager", END)

        return workflow
