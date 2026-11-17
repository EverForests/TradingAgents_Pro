import json
import logging
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

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
from tradingagents.agents.verified_metrics import VERIFIED, verify_metric
from tradingagents.dataflows.date_window import as_of

from .analyst_execution import build_analyst_execution_plan
from .conditional_logic import ConditionalLogic

logger = logging.getLogger(__name__)

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

# The market analyst's tool whose reply ends in the quote's own source line.
# It is the only tool this step reads; the statement tools keep their behaviour.
_QUOTE_TOOL = "get_verified_market_snapshot"
_QUOTE_SOURCE_PREFIX = "# FR02_QUOTE_SOURCE "


def _tools_or_done(state) -> str:
    """Route an analyst's turn: run its tool calls, or finish with its report."""
    return "tools" if state["messages"][-1].tool_calls else END


# --- The market snapshot's quote source -------------------------------------


def _quote_source_line(text):
    """The quote source on the reply's own last line, or None.

    Only the final nonblank line is considered, and it must carry exactly the
    source prefix. Numbers are parsed with ``Decimal`` so the vendor's precision
    survives the trip through JSON.
    """
    lines = [line for line in str(text if text is not None else "").splitlines() if line.strip()]
    if not lines or not lines[-1].startswith(_QUOTE_SOURCE_PREFIX):
        return None
    try:
        payload = json.loads(lines[-1][len(_QUOTE_SOURCE_PREFIX):], parse_float=Decimal)
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _decimal(value):
    """An exact finite Decimal from a JSON number or numeric string, or None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int):
        number = Decimal(value)
    elif isinstance(value, float):
        number = Decimal(repr(value))
    elif isinstance(value, str):
        try:
            number = Decimal(value.strip())
        except (InvalidOperation, ValueError):
            return None
    else:
        return None
    return number if number.is_finite() else None


def _is_quote_currency(unit) -> bool:
    """Whether a unit is a three-letter uppercase currency code."""
    return (isinstance(unit, str) and len(unit) == 3
            and unit.isascii() and unit.isalpha() and unit.isupper())


def _calendar_date(value):
    """A date built from an ISO YYYY-MM-DD string, or None."""
    import datetime

    text = value.strip() if isinstance(value, str) else ""
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        return None
    try:
        parsed = datetime.date.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == text else None


def _valid_run(state):
    """This invocation's course_run, or None when there is none to scope a record to."""
    run = state.get("course_run") if isinstance(state, dict) else None
    if not isinstance(run, dict):
        return None
    if not all(isinstance(run.get(field), str) and run.get(field).strip()
               for field in ("run_id", "ticker", "as_of_date")):
        return None
    return run


def _effective_cutoff(state, call, run):
    """The effective as-of date for this call, or None when it is not this run's.

    The state's own company and analysis date must be the ones the run records,
    and the run's date must itself be a real calendar date: an invalid one is a
    missing source, not something to raise out of a tool node. The cutoff then
    follows the data layer's own rule for the call's requested day — a missing
    ``curr_date`` falls back to the analysis date there — and it may never run
    past the analysis date.
    """
    if not isinstance(state, dict):
        return None
    company = state.get("company_of_interest")
    trade_date = state.get("trade_date")
    if not isinstance(company, str) or company.strip().upper() != run["ticker"].strip().upper():
        return None
    if not isinstance(trade_date, str) or trade_date.strip() != run["as_of_date"].strip():
        return None
    analysis = _calendar_date(run["as_of_date"])
    if analysis is None:
        return None
    args = call.get("args") or {}
    requested = args.get("curr_date") if isinstance(args, dict) else None
    try:
        cutoff = _calendar_date(str(as_of(requested, trade_date)))
    except (TypeError, ValueError):
        return None
    if cutoff is None or cutoff > analysis:
        return None
    return cutoff


def _quote_request(payload, run, cutoff):
    """The C2 price gap the snapshot states, or None when it is not verifiable here.

    The stock must be this run's, the reply's stated cutoff the effective one,
    the trading day a real date that is not later than that cutoff (a weekend or
    holiday is served by the last trading day before it, and an explicitly
    earlier query is allowed too), the currency a plain code, and both figures
    finite. Field, day and currency are the ones the Yahoo snapshot reported.
    """
    if payload.get("as_of_date") != cutoff.isoformat():
        return None
    symbol = payload.get("symbol")
    if not isinstance(symbol, str) or symbol.strip().upper() != run["ticker"].strip().upper():
        return None
    trading_day = _calendar_date(payload.get("trading_date"))
    if trading_day is None or trading_day > cutoff:
        return None
    currency = payload.get("currency")
    if not _is_quote_currency(currency):
        return None
    close = _decimal(payload.get("close"))
    upper = _decimal(payload.get("boll_ub"))
    if close is None or upper is None:
        return None

    instant = {"kind": "instant", "start": trading_day.isoformat(),
               "end": trading_day.isoformat(), "label": f"{trading_day.isoformat()} quote"}
    source = f"quote:{run['ticker'].strip().upper()}:{trading_day.isoformat()}"
    return {"kind": "price_delta", "operands": [
        {"role": "current", "value": str(upper), "unit": currency,
         "period": dict(instant), "source_ref": source, "field_ref": "boll_ub"},
        {"role": "reference", "value": str(close), "unit": currency,
         "period": dict(instant), "source_ref": source, "field_ref": "Close"},
    ]}


def _quote_outcome(request, reply):
    """The reply unchanged, or a Command that also hands over the verified price gap.

    Only the market tool's own successful reply is read, matched to its call by
    name and ID and by the reply carrying that ID. A reply with no usable source,
    a run that is not this invocation's, or a metric the module refuses all
    return the reply exactly as it was: nothing is invented and no run is made.
    """
    call = getattr(request, "tool_call", None) or {}
    if not isinstance(call, dict) or call.get("name") != _QUOTE_TOOL:
        return reply
    call_id = call.get("id")
    if not isinstance(reply, ToolMessage):
        return reply
    if not call_id or reply.tool_call_id != call_id or reply.name != call["name"]:
        return reply
    if getattr(reply, "status", "success") == "error":
        return reply
    state = getattr(request, "state", None) or {}
    run = _valid_run(state)
    if run is None:
        return reply
    cutoff = _effective_cutoff(state, call, run)
    if cutoff is None:
        return reply
    payload = _quote_source_line(reply.content)
    if payload is None:
        return reply
    request_body = _quote_request(payload, run, cutoff)
    if request_body is None:
        return reply

    result = verify_metric(request_body, run)
    if not isinstance(result, dict) or result.get("status") != VERIFIED:
        return reply
    metric = result.get("metric")
    if not isinstance(metric, dict) or not metric.get("metric_id"):
        return reply
    return Command(update={
        "messages": [reply],
        "verified_metrics": {metric["metric_id"]: metric},
    })


# --- The statement tools' filed facts ----------------------------------------
#
# The two statement replies end in a source array, one entry per printed cell.
# Only a successful reply of the tool that was actually called is read, and
# only through the same name, ID, run and effective cutoff the quote path uses.
# A fact is cited only when its own record is complete and its period, unit and
# scale can be stated exactly; the metric module then decides whether the pair
# it forms is comparable.

_STATEMENT_SOURCE_PREFIX = "# FR02_SEC_SOURCE "
_INCOME_TOOL = "get_income_statement"
_CASHFLOW_TOOL = "get_cashflow"
_YOY_ITEMS = ("Revenue", "Cost of Revenue")
_FREQUENCIES = ("quarterly", "annual")

_MILLIONS = Decimal(1000000)
_YEAR_DAYS = (300, 400)
_QUARTER_DAYS = (60, 115)


def _statement_source_array(text):
    """The statement's source array on the reply's own last line, or None.

    Only the final nonblank line is considered and it must carry exactly the
    prefix; numbers keep their precision through ``Decimal``. A missing prefix,
    unreadable JSON or a payload that is not a list reads as no source.
    """
    lines = [line for line in str(text if text is not None else "").splitlines() if line.strip()]
    if not lines or not lines[-1].startswith(_STATEMENT_SOURCE_PREFIX):
        return None
    try:
        payload = json.loads(lines[-1][len(_STATEMENT_SOURCE_PREFIX):], parse_float=Decimal)
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, list) else None


def _stated_fact(entry, run, cutoff, freq):
    """(fact, period) for one citable source entry, or None.

    The entry must name this run's stock and the effective cutoff; carry the
    filer's CIK, tag, accession, item, period and span; have a period equal to
    the fact's own end and a span of integer 0 (the quarter or year itself, not
    a year-to-date column); state real dates with start not after end, and neither
    the period end nor the filing date after the cutoff; and carry a finite
    non-boolean value whose scale is the one its unit uses — USD printed in
    millions divides by 1,000,000, any other unit is kept only at exactly 1.
    The period must also cover one span of the call's own frequency.
    """
    if not isinstance(entry, dict):
        return None
    ticker = entry.get("ticker")
    if not isinstance(ticker, str) or ticker.strip().upper() != run["ticker"].strip().upper():
        return None
    if entry.get("as_of") != cutoff.isoformat():
        return None
    for field in ("cik", "tag", "accn", "item", "period"):
        if not isinstance(entry.get(field), str) or not entry.get(field).strip():
            return None

    span = entry.get("span")
    if isinstance(span, bool) or not isinstance(span, int) or span != 0:
        return None

    start = _calendar_date(entry.get("start"))
    end = _calendar_date(entry.get("end"))
    filed = _calendar_date(entry.get("filed"))
    if start is None or end is None or filed is None:
        return None
    if start > end or end > filed or filed > cutoff:
        return None
    if _calendar_date(entry.get("period")) != end:
        return None

    days = (end - start).days + 1
    low, high = _QUARTER_DAYS if freq == "quarterly" else _YEAR_DAYS
    if not low <= days <= high:
        return None

    raw = _decimal(entry.get("value"))
    if raw is None:
        return None
    unit = entry.get("unit")
    if not isinstance(unit, str) or not unit.strip():
        return None
    divisor = _decimal(entry.get("display_divisor"))
    if divisor is None:
        return None
    if unit.strip() == "USD":
        if divisor != _MILLIONS:
            return None
        value, scaled = raw / divisor, "USD_millions"
    else:
        if divisor != Decimal(1):
            return None
        value, scaled = raw, unit.strip()

    fact = {
        "item": entry["item"].strip(),
        "tag": entry["tag"].strip(),
        "accn": entry["accn"].strip(),
        "cik": entry["cik"].strip(),
        "start": start,
        "end": end,
        "filed": filed,
        "value": value,
        "unit": scaled,
    }
    period = {"kind": "quarter" if freq == "quarterly" else "year",
              "start": start.isoformat(), "end": end.isoformat(),
              "label": "{} {}..{}".format(fact["item"], start.isoformat(), end.isoformat())}
    return fact, period


def _fact_operand(role, fact, period):
    """A C2 operand for one cited fact: its exact value, period, item and filing."""
    return {
        "role": role,
        "value": str(fact["value"]),
        "unit": fact["unit"],
        "period": dict(period),
        "source_ref": "sec:{}:{}:{}:{}..{}:filed {}".format(
            fact["cik"], fact["accn"], fact["tag"],
            fact["start"].isoformat(), fact["end"].isoformat(), fact["filed"].isoformat()),
        "field_ref": fact["item"],
    }


def _year_apart(prior_end, current_end):
    """Whether two period ends sit one year apart, give or take a week."""
    try:
        anniversary = prior_end.replace(year=prior_end.year + 1)
    except ValueError:                      # 29 February
        anniversary = prior_end.replace(year=prior_end.year + 1, day=28)
    return abs((current_end - anniversary).days) <= 7


def _attempt_yoy(attempt, rows):
    """Try each current period against the newest comparable one a year earlier.

    Rows are newest first. Stops at the first pair the module signs; a current
    row with no candidate, or one whose candidates are all refused, leaves the
    search to the next row.
    """
    for index, (current, current_period) in enumerate(rows):
        current_end = current["end"]
        if index and rows[index - 1][0]["end"] == current_end:
            continue                        # the same end already tried
        for prior, prior_period in rows[index + 1:]:
            if prior["end"] >= current_end:
                continue
            if prior["unit"] != current["unit"] or prior["cik"] != current["cik"]:
                continue
            if prior_period["kind"] != current_period["kind"]:
                continue
            if not _year_apart(prior["end"], current_end):
                continue
            if attempt("yoy", [
                _fact_operand("current", current, current_period),
                _fact_operand("prior", prior, prior_period),
            ]):
                return True
    return False


def _signed_statement_requests(payload, run, cutoff, freq, tool_name):
    """The records this reply's own facts sign, by ID.

    Each pair is formed from cited facts and offered to ``verify_metric`` as it
    is found, so a refusal moves on to the next candidate rather than ending the
    search. Revenue and Cost of Revenue are paired with their own latest
    comparable period; the cash-flow statement pairs capital expenditure with
    operating cash flow inside this one reply, on the same start and end and the
    same unit. A missing partner signs nothing and nothing is combined across
    replies.
    """
    cited = []
    for entry in payload:
        found = _stated_fact(entry, run, cutoff, freq)
        if found is not None:
            cited.append(found)

    issued = {}

    def attempt(kind, operands):
        result = verify_metric({"kind": kind, "operands": operands}, run)
        if not isinstance(result, dict) or result.get("status") != VERIFIED:
            return False
        metric = result.get("metric")
        if not isinstance(metric, dict) or not metric.get("metric_id"):
            return False
        issued[metric["metric_id"]] = metric
        return True

    if tool_name == _INCOME_TOOL:
        for item in _YOY_ITEMS:
            rows = sorted((found for found in cited if found[0]["item"] == item),
                          key=lambda found: (found[0]["end"], found[0]["start"]), reverse=True)
            _attempt_yoy(attempt, rows)
    else:
        groups = {}
        for fact, period in cited:
            groups.setdefault((fact["start"], fact["end"]), {})[fact["item"]] = (fact, period)
        for span in sorted(groups, reverse=True):
            rows = groups[span]
            numerator = rows.get("Capital Expenditure")
            denominator = rows.get("Operating Cash Flow")
            if numerator is None or denominator is None:
                continue
            if numerator[0]["unit"] != denominator[0]["unit"]:
                continue
            if numerator[0]["cik"] != denominator[0]["cik"]:
                continue
            attempt("ratio", [
                _fact_operand("numerator", numerator[0], numerator[1]),
                _fact_operand("denominator", denominator[0], denominator[1]),
            ])
    return issued


def _statement_outcome(request, reply):
    """The reply unchanged, or a Command that also hands over this reply's records.

    Only the two statement tools' own successful replies are read, matched to
    their call by name and ID and by the reply carrying that ID; the frequency
    is the one the call actually made, quarterly when it named none. A reply
    with no source array, a run that is not this invocation's, or figures the
    module refuses all return the reply exactly as it was. A reply that does
    yield records is still passed on once, unchanged.
    """
    call = getattr(request, "tool_call", None) or {}
    if not isinstance(call, dict) or call.get("name") not in (_INCOME_TOOL, _CASHFLOW_TOOL):
        return reply
    call_id = call.get("id")
    if not isinstance(reply, ToolMessage):
        return reply
    if not call_id or reply.tool_call_id != call_id or reply.name != call["name"]:
        return reply
    if getattr(reply, "status", "success") == "error":
        return reply
    state = getattr(request, "state", None) or {}
    run = _valid_run(state)
    if run is None:
        return reply
    cutoff = _effective_cutoff(state, call, run)
    if cutoff is None:
        return reply
    payload = _statement_source_array(reply.content)
    if payload is None:
        return reply

    args = call.get("args") or {}
    freq = args.get("freq") if isinstance(args, dict) else None
    freq = freq.strip().lower() if isinstance(freq, str) and freq.strip() else "quarterly"
    if freq not in _FREQUENCIES:
        return reply

    issued = _signed_statement_requests(payload, run, cutoff, freq, call["name"])
    if not issued:
        return reply
    return Command(update={"messages": [reply], "verified_metrics": issued})


def _analyst_graph(spec, agent, max_tool_rounds: int):
    """One analyst as a graph of its own: the model and its tools, on a private message history.

    It returns only its report, so analysts running side by side never write the
    same key, and its tool calls never reach the other analysts' messages. After
    ``max_tool_rounds`` rounds of tool calls it is told to write its report, and
    that turn ends it whatever it answers, so a model that keeps calling tools
    cannot run the graph into its recursion limit (#1420).

    The market and fundamentals analysts also return this run's verified
    metrics, handed to them by their own tool nodes while the tool results
    themselves stay unchanged.
    """
    schema = {spec.report_key: str}
    if spec.key in ("market", "fundamentals"):
        # Feeding the parent's registry when it already has records keeps the
        # merge semantics the state already defines; an empty start would be
        # dropped rather than merged.
        schema["verified_metrics"] = dict
    output = TypedDict(f"{spec.key.capitalize()}Report", schema)
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

    if spec.key == "market":
        def wrap_tool_call(request, execute):
            """The stock node's own result, then the quote source it carries."""
            return _quote_outcome(request, execute(request))

        async def awrap_tool_call(request, execute):
            """The stock node's own awaited result, then the quote source it carries."""
            return _quote_outcome(request, await execute(request))
    elif spec.key == "fundamentals":
        def wrap_tool_call(request, execute):
            """The stock node's own result, then the facts its cells cite."""
            return _statement_outcome(request, execute(request))

        async def awrap_tool_call(request, execute):
            """The stock node's own awaited result, then the facts its cells cite."""
            return _statement_outcome(request, await execute(request))
    if spec.key in ("market", "fundamentals"):
        tool_node = ToolNode(list(spec.tools), wrap_tool_call=wrap_tool_call,
                             awrap_tool_call=awrap_tool_call)
    else:
        tool_node = ToolNode(list(spec.tools))
    graph.add_node("tools", tool_node)
    graph.add_node("wrap_up", wrap_up)
    graph.add_conditional_edges("agent", _tools_or_done, ["tools", END])
    graph.add_conditional_edges("tools", more_or_wrap_up, ["agent", "wrap_up"])
    graph.add_edge("wrap_up", END)
    return graph.compile()


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
        for node in first_steps:
            workflow.add_edge(START, node)
        workflow.add_edge(first_steps, "Bull Researcher")

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
