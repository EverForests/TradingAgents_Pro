"""FR-01 R8-B — market snapshot collection: window, retained material, wrap_up.

Baseline: ``712617e25a380197e38d6ee5cc4dcc7ab393cf61``; contracts C0/C1 v1.0.
Approved plan: R8-B §4, supplementary note §3 (W-A, ``source_ref``, ``content_ref``,
``effective_as_of``) and the newly readable §5.5 sources:

- ``tradingagents/agents/tools.py`` — ``get_verified_market_snapshot`` is a
  ``@tool``; its model-facing args are ``curr_date`` and ``look_back_days`` while
  ``symbol`` and ``trade_date`` are injected from graph state. Vendor failures come
  back as text placeholders (``vendor_unavailable`` / ``no_data_available``), never
  as exceptions.
- ``tradingagents/agents/analysts/market_analyst.py`` — the market analyst offers
  ``get_stock_data``, ``get_indicators`` and ``get_verified_market_snapshot`` and
  calls ``take_turn`` once per graph step; ``wrap_up`` re-invokes it after the
  tool-round limit.
- ``tradingagents/dataflows/vendors/yahoo/snapshot.py`` — the verified snapshot
  renders a "### Recent verified closes" ``| Date | Close |`` table whose rows are
  ``max(1, min(int(look_back_days), 30))`` and whose dates are ``YYYY-MM-DD``.
- ``tradingagents/dataflows/vendors/yahoo/ohlcv.py`` — ``load_ohlcv`` returns a
  ``Date, Open, High, Low, Close, Volume`` frame for one symbol no later than the
  requested date; the snapshot calls it with ``fill_gaps=False``.
- ``tradingagents/dataflows/date_window.py`` — ``as_of(curr_date, trade_date)``
  clamps the model's date to the run's date.

Design of this file:

* The **real collection chain** runs: the real ``@tool`` closure, the real
  ``build_verified_market_snapshot`` over a fixed OHLCV frame, the real snapshot
  ``as_of`` clamp. Only the ``load_ohlcv`` call inside ``snapshot`` is replaced by
  that fixed frame, and only the collector is the object under test.
* The tool is driven two ways: a direct ``invoke`` for helper calls that states
  every argument (``symbol`` and ``trade_date`` included, because a bare tool has
  no graph to inject them), and a real ``ToolNode`` inside a compiled graph, which
  injects them the way the analyst subgraph does. The model never sends
  ``symbol``. ``look_back_days`` is typed ``int`` on the tool, so the tests pass
  an int, never a string.
* The snapshot's rows are read from the ``| Date | Close |`` table under its
  heading, skipping the blank line and header block first, and every close is
  normalised to one canonical decimal string, so a row, the latest close, the
  fixture and the window assertions all compare the same representation.
* Window ``W-A`` (note §3.2) is verified against the rows the snapshot actually
  shows: first and last row date, ISO format, end <= the run date, row count
  ``max(1, min(int(look_back_days), 30))``.
* ``content_ref`` must resolve back to retained material under the retention root
  (``{results_dir}/{safe_ticker}/{trade_date}/evidence/{run_id}/``).
* ``wrap_up`` is exercised on the **production analyst subgraph**: the case builds
  it with ``tradingagents.graph.setup._analyst_graph`` plus the production analyst
  plan and ``create_market_analyst``. The fake model's two branches are
  ``Runnable``s, so the production prompt can pipe its ``PromptValue`` into
  either; the bound branch emits the snapshot ``tool_calls`` and the unbound one
  produces the report. After ``max_tool_rounds`` the production wrap-up turn runs
  unbound, produces ``market_report`` and passes both tool results to it. If that
  wiring cannot be imported, the case names it and skips rather than substituting
  a copy.
* Negative cases: vendor error/no-data placeholders, report-only runs (no tool
  call), unreadable retained material, and a foreign run's evidence.
* The unreadable-material case begins with the positive control the acceptance
  needs: a usable snapshot **must** mint a record, so an implementation that
  refuses every snapshot fails the case instead of passing it vacuously. Only
  then is the retained material deleted.

Running this file on its own:

* Every helper imports ``tradingagents.graph.trading_graph`` **before** the
  agent or graph fragment it needs, and ``_snapshot_text`` does the same before
  importing the tool. That is the project's own entry order (``cli/run.py``
  imports it first, and it imports ``tradingagents.agents`` before
  ``setup``/``propagation``), so the module graph is built in production order
  whether or not another test file has already loaded it. Importing
  ``tradingagents.graph.setup`` or ``tradingagents.agents`` first produced the
  circular import seen when this file ran alone.

BLOCKED dependences, recorded here rather than hidden:

* A baseline **skip is not B acceptance**. ``evidence_collection.py`` (the
  collector the plan allocates to FR-01) does not exist at this baseline, so the
  collection cases call ``pytest.skip`` with a reason naming the missing symbol
  and a baseline run reports them as **skipped, not passed**. They are
  post-implementation obligations that must execute.
* The cases that do NOT need the collector (the fixed frame, the direct tool
  call, the real ``ToolNode`` injection inside a compiled graph, the window clamp,
  the date clamp and the wrap-up subgraph) collect and run at the baseline, so the
  real snapshot chain and the analyst subgraph are verified even before
  implementation. Those cases never skip: an import, config or fake-model error in
  them fails the run instead. Nothing is marked ``blocked``: the marker would hide
  those runnable cases.
* Nothing in the approved plan states the collector's callable name or its return
  type, and no source defines it yet. This file therefore drives it through one
  small adapter, :func:`_collect`, the single place to update when the
  implementation fixes the entry point. Every assertion below the adapter is
  contract text (R8-B / C0 / C1) and does not depend on the adapter's shape.
* ``tradingagents/dataflows/symbols.py`` (``normalize_symbol`` /
  ``safe_ticker_component``), ``router.py`` (placeholder text) and ``errors.py``
  were denied, so the vendor input is pinned at ``load_ohlcv`` (readable, §5.5)
  rather than at the cache file whose name needs ``safe_ticker_component``, and
  the expectation is "no record, no retained material" rather than the router's
  exact wording. The vendor-failure cases need the error types the tool itself
  catches (``tradingagents.dataflows.errors``), which were denied to the agent;
  each of those cases attempts that import inside its body and, if the import is
  the failing step, reports as a collection/import error rather than a pass.
* Paths still denied to the agent, so not read or cited directly:
  ``tradingagents/dataflows/symbols.py``, ``tradingagents/dataflows/router.py``,
  ``tradingagents/dataflows/errors.py``, ``tradingagents/graph/__init__.py``,
  ``tradingagents/graph/analyst_execution.py``, ``tradingagents/reporting/`` and
  ``tradingagents/memory/{reflection,settlement,store}.py``.
  ``setup.py`` and ``trading_graph.py`` (which this file relies on) are readable.
  If ``setup._analyst_graph`` or ``analyst_execution`` cannot be imported at run
  time, the wrap_up case skips with a reason naming the missing production wiring
  — production wiring verification is then still outstanding.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pandas as pd
import pytest

# --- fixed run identity (C0) --------------------------------------------------

CONTRACT_VERSION = "1.0"
TICKER = "AAPL"
TRADE_DATE = "2026-11-10"
RUN_A = "run-a-0001"
RUN_B = "run-b-0002"
REQUEST_LIMIT = 40

TOOL_NAME = "get_verified_market_snapshot"
# The heading line the snapshot renders, without its row count; rows are read
# from the ``| Date | Close |`` table under it.
SNAPSHOT_HEADING = "### Recent verified closes"

# The fixed OHLCV frame: five consecutive business days ending on the run date.
# Business-day rows keep the "Recent verified closes" window deterministic.
# Closes are written as the canonical decimal strings the snapshot renders, so a
# row, the latest close and this fixture can all be compared as parsed.
FIXED_ROWS = (
    # (date,        open,    high,    low,     close,   volume)
    ("2026-11-04", "341.10", "344.20", "340.05", "344.02", 51_200_000),
    ("2026-11-05", "344.02", "347.80", "343.10", "347.55", 49_800_000),
    ("2026-11-06", "347.55", "350.10", "346.20", "349.90", 52_500_000),
    ("2026-11-09", "349.90", "352.30", "348.80", "351.60", 47_300_000),
    ("2026-11-10", "351.60", "353.40", "347.90", "348.245", 55_100_000),
)
LATEST_CLOSE = "348.245"


def _fixed_frame() -> pd.DataFrame:
    """The fixed OHLCV DataFrame in the column layout ``load_ohlcv`` produces."""
    return pd.DataFrame(
        [
            {
                "Date": date,
                "Open": float(open_),
                "High": float(high),
                "Low": float(low),
                "Close": float(close),
                "Volume": volume,
            }
            for date, open_, high, low, close, volume in FIXED_ROWS
        ],
        columns=["Date", "Open", "High", "Low", "Close", "Volume"],
    )


def _run_context(run_id: str) -> dict:
    """A complete RunContext as R8-B §1 specifies it."""
    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "ticker": TICKER,
        "as_of_date": TRADE_DATE,
        "execution_status": "COMPLETED",
        "request_limit": REQUEST_LIMIT,
    }


def _graph_state(trade_date: str = TRADE_DATE) -> dict:
    """The state ``get_verified_market_snapshot`` reads its injected args from."""
    return {"company_of_interest": TICKER, "trade_date": trade_date}


# --- the real snapshot tool ----------------------------------------------------


def _pin_ohlcv(monkeypatch, frame: pd.DataFrame | None = None) -> list[tuple]:
    """Serve the fixed frame in place of the vendor download; returns the calls made.

    ``build_verified_market_snapshot`` calls ``load_ohlcv`` (readable at §5.5).
    Replacing that one call keeps the real snapshot rendering, the real ``as_of``
    clamp and the real ``@tool`` closure, while the vendor input is the fixed
    frame. ``load_ohlcv`` is imported into ``snapshot`` by name, so the module
    attribute is what the snapshot reads.
    """
    import tradingagents.dataflows.vendors.yahoo.snapshot as snapshot

    data = frame if frame is not None else _fixed_frame()
    calls: list[tuple] = []

    def _load(symbol, as_of_date, fill_gaps=True):
        calls.append((symbol, as_of_date, fill_gaps))
        return data.copy()

    monkeypatch.setattr(snapshot, "load_ohlcv", _load)
    return calls


def _snapshot_text(curr_date: str = TRADE_DATE, look_back_days: int = 7,
                   trade_date: str = TRADE_DATE) -> str:
    """Run the real snapshot tool for a helper call, with every argument given.

    The project's graph entry is imported **first** so this file runs on its own
    with the module graph built in production order (see the header).

    A bare ``@tool`` call has no graph around it, so nothing injects the tool's
    ``InjectedState`` arguments: ``symbol`` and ``trade_date`` are stated in the
    input dict here, together with the model-facing ``curr_date`` and
    ``look_back_days``. A ``state=`` keyword does not stand in for them — that is
    the graph's job, and this helper is not a graph. The ``ToolNode`` case below
    covers the injected path the analyst subgraph actually uses.
    """
    _import_graph_entry()
    from tradingagents.agents.tools import get_verified_market_snapshot

    return get_verified_market_snapshot.invoke({
        "symbol": TICKER,
        "trade_date": trade_date,
        "curr_date": curr_date,
        "look_back_days": look_back_days,
    })


# --- the real tool node and analyst subgraph -----------------------------------
#
# Why these helpers exist: this file must run on its own. The project's own
# entry order is ``tradingagents.graph.trading_graph`` (``cli/run.py`` imports it
# first), which in turn imports ``tradingagents.agents`` and only then ``setup``
# and ``propagation``; importing pieces of the analyser before that order is
# established is what produced the circular import seen when this file ran
# alone. Every helper below therefore imports ``trading_graph`` **first**, then
# the fragment it needs, so the module graph is built in production order
# whether or not another test file has already loaded it.


def _import_graph_entry():
    """Import the project's normal graph entry first, then return its module."""
    import tradingagents.graph.trading_graph as tg  # noqa: F401  (entry order matters)

    return tg


def _tool_node(spec_tools):
    """A real ``ToolNode`` over the given tools, as ``setup._analyst_graph`` builds."""
    _import_graph_entry()
    from langgraph.prebuilt import ToolNode

    return ToolNode(list(spec_tools))


def _tool_graph(spec_tools):
    """A compiled graph whose only node is the real ``ToolNode`` over ``spec_tools``.

    A ``ToolNode`` cannot be driven on its own: ``InjectedState`` arguments are
    filled from the graph runtime, so a bare ``ToolNode.invoke`` fails with
    "Missing required config key" before the tool is reached. Inside a compiled
    graph the same node receives the run state and injects ``symbol`` and
    ``trade_date`` exactly as the analyst subgraph does.
    """
    _import_graph_entry()
    from langgraph.graph import END, START, StateGraph

    from tradingagents.agents.state import AgentState

    graph = StateGraph(AgentState)
    graph.add_node("tools", _tool_node(spec_tools))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    return graph.compile()


def _market_analyst_subgraph(llm, max_tool_rounds: int):
    """The market analyst wired by the **production** ``setup._analyst_graph``.

    ``_analyst_graph(spec, agent, max_tool_rounds)`` is not copied here: the spec
    comes from the production analyst plan, the agent from the production
    ``create_market_analyst`` and the subgraph from the production factory, so
    what this case runs is the graph the application runs, including its real
    ``ToolNode`` (which injects ``symbol``/``trade_date`` from the state) and its
    own ``wrap_up`` turn.

    The factory is read through ``setup``'s module attribute rather than by name,
    because it is private; a rename surfaces as the assertion below instead of an
    ImportError. If the import of ``setup`` itself is denied/unavailable, the case
    reports the missing production wiring rather than falling back to a copy.
    """
    _import_graph_entry()
    from langchain_core.messages import HumanMessage
    from langchain_core.runnables import RunnableLambda

    from tradingagents.agents.analysts.market_analyst import create_market_analyst
    from tradingagents.agents.analysts.turn import WRAP_UP

    try:
        import tradingagents.graph.setup as setup
        from tradingagents.graph.analyst_execution import build_analyst_execution_plan
    except ImportError as exc:  # the production wiring is not reachable
        pytest.skip(
            "the production analyst subgraph wiring is not reachable from this test "
            f"({type(exc).__name__}: {exc}); the wrap_up case must use "
            "setup._analyst_graph and cannot be verified until it can be imported"
        )

    factory = getattr(setup, "_analyst_graph", None)
    assert factory is not None, (
        "setup._analyst_graph is missing: the wrap_up case verifies the production "
        "analyst wiring and will not substitute a copy of it"
    )
    plan = build_analyst_execution_plan(("market",))
    spec = next(s for s in plan.specs if s.key == "market")
    assert TOOL_NAME in [t.name for t in spec.tools], (
        f"the market analyst's plan no longer offers {TOOL_NAME}: {[t.name for t in spec.tools]}"
    )

    # The production ``take_turn`` classifies the closing turn by the last human
    # message being exactly ``WRAP_UP``; recording it lets the case assert that the
    # only unbound turn was that one, instead of assuming it.
    def _as_messages(prompt) -> list:
        """The prompt as a message list, whichever form the caller passed."""
        to_messages = getattr(prompt, "to_messages", None)
        return to_messages() if callable(to_messages) else list(prompt)

    def _is_wrap_up(messages) -> bool:
        return (
            bool(messages)
            and isinstance(messages[-1], HumanMessage)
            and messages[-1].content == WRAP_UP
        )

    class _Marker:
        """A model that records how each turn was reached, then defers to ``llm``.

        ``take_turn`` pipes its prompt into the bound or the plain branch, so each
        branch is a ``Runnable`` that takes the ``PromptValue``, converts it to a
        message list for recording and then hands it to the fake model's matching
        branch. The fake's bound branch is the one that actually emits
        ``tool_calls``; this wrapper only observes how the production wiring
        reached it (tools bound, plain turn, or the wrap-up history).
        """

        def __init__(self):
            self.turns: list[dict] = []
            self.bound_turns = 0

        def bind_tools(self, tools, **kwargs):
            bound = llm.bind_tools(tools, **kwargs)

            def _turn(prompt):
                self.bound_turns += 1
                self.turns.append({"wrap_up": _is_wrap_up(_as_messages(prompt)), "tools_bound": True})
                return bound.invoke(prompt)

            return RunnableLambda(_turn)

        def invoke(self, prompt):
            # Reached unbound: ``take_turn`` only does that for a wrap-up turn.
            self.turns.append({"wrap_up": _is_wrap_up(_as_messages(prompt)), "tools_bound": False})
            return llm.invoke(prompt)

        # ``prompt | llm`` treats its right-hand side as a runnable, so the wrap-up
        # turn calls the object rather than ``invoke``: it must be callable too.
        __call__ = invoke

    marker = _Marker()
    return factory(spec, create_market_analyst(marker), max_tool_rounds), marker


_CLOSE_COLUMNS = ("Date", "Close")
_BLANK_OR_RULE = {"", "---", "---:", ":---", ":---:"}


def _snapshot_rows(text: str) -> list[tuple[str, str]]:
    """The ``(date, close)`` trading rows of the "Recent verified closes" table.

    The snapshot renders a blank line, then a ``| Date | Close |`` header, a
    ``|---:|---:|`` rule and the rows, so the header block comes *before* the
    body: the blank line and the two header lines are skipped, and reading starts
    only once the ``Date | Close`` header has been seen. Reading stops at the
    first non-table line after the body, so the table's extent is the same as
    before. Other tables in the snapshot never satisfy the two-column header
    check, so this reader cannot wander into them.
    """
    rows: list[tuple[str, str]] = []
    seen_header = False
    for line in text.splitlines():
        stripped = line.strip()
        if not seen_header:
            if tuple(c.strip() for c in stripped.strip("|").split("|")) == _CLOSE_COLUMNS:
                seen_header = True
            continue
        if not stripped.startswith("|"):
            break
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) != 2:
            continue
        date, close = cells
        if date.lower() in ("date", "---") or date in _BLANK_OR_RULE:
            continue
        if set(date) <= {"-", ":", " "}:
            continue
        rows.append((date, _price(close)))
    return rows


def _price(value: str) -> str:
    """One price representation: the canonical decimal string, whatever the format.

    ``348.245``, ``348.2450`` and ``$348.25`` all read the same, so a row, the
    latest close and the fixture can be compared directly.
    """
    from decimal import Decimal, InvalidOperation

    text = str(value).strip().replace(",", "").lstrip("$")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return text
    normalized = format(number.normalize(), "f")
    return normalized


def _table_rows(text: str) -> list[tuple[str, str]]:
    """The rows of the "Recent verified closes" table, and only that table."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower().startswith(SNAPSHOT_HEADING.lower()):
            return _snapshot_rows("\n".join(lines[index + 1:]))
    return []


def _recent_rows(text: str) -> list[tuple[str, str]]:
    """The ``(date, close)`` rows of the "Recent verified closes" table, closes canonical."""
    return _table_rows(text)


# --- the collector under test --------------------------------------------------


_BLOCKED_REASON = (
    "FR-01 B not implemented at this baseline: {missing} is absent; the market "
    "snapshot collection contract (R8-B §4 / note §3) cannot be exercised, so this "
    "case must be executed after implementation and must not be counted as a pass"
)


def _collector_callable():
    """The approved collector, or ``None`` while it does not exist.

    R8-B allocates the collector to ``tradingagents/agents/evidence_collection.py``.
    No baseline source defines its callable name or signature, so this helper is
    the only place the name is written; the assertions below are contract text.
    """
    try:
        module = importlib.import_module("tradingagents.agents.evidence_collection")
    except ModuleNotFoundError:
        return None
    return getattr(module, "record_market_snapshot", None)


def _collect(tool_call: dict, tool_response: str, state: dict, run: dict,
             results_dir: Path) -> dict:
    """Collect one snapshot response into a v1 EvidenceRecord (or a receipt).

    ``tool_call`` is the paired call as the graph stores it (``id``, ``name``,
    ``args``); ``tool_response`` is the tool's returned text; ``run`` is the
    RunContext of the *current* run.

    Fails through to the caller when the collector is missing so the caller's
    ``pytest.skip`` can name the gap; never fabricates a record.
    """
    collector = _collector_callable()
    if collector is None:
        raise _CollectorMissing("record_market_snapshot")

    return collector(
        tool_call=tool_call,
        tool_response=tool_response,
        state=state,
        run=run,
        results_dir=str(results_dir),
    )


class _CollectorMissing(Exception):
    """Raised when the collector the plan allocates has not been implemented."""


def _require_collector():
    if _collector_callable() is None:
        pytest.skip(_BLOCKED_REASON.format(
            missing="tradingagents.agents.evidence_collection.record_market_snapshot"))


def _paired_call(call_id: str = "call-1", curr_date: str = TRADE_DATE,
                 look_back_days: int = 7) -> dict:
    """A tool call as ``tool_calls[*]`` carries it: the args the model sent."""
    return {
        "id": call_id,
        "type": "tool_call",
        "name": TOOL_NAME,
        "args": {"curr_date": curr_date, "look_back_days": look_back_days},
    }


def _paired_tool_result(text: str, call: dict) -> dict:
    """The tool result as the graph history pairs it with its call (``ToolMessage``)."""
    return {"tool_call_id": call["id"], "name": call["name"], "content": text}


def _paired_state(text: str, call: dict | None = None) -> dict:
    """The run state carrying the snapshot call and its response, as the graph keeps them.

    The collector binds a record to the call it came from, so the run state it is
    given must hold that pair. ``tool_calls`` / ``tool_results`` are the pairing
    surfaced in plain form; the agent-facing ``messages`` hold the same pair as
    ``AIMessage``/``ToolMessage``, so a collector reading either shape finds it.
    A report-only run pairs nothing and passes no pair.
    """
    call = call if call is not None else _paired_call()
    return {
        **_graph_state(),
        **_paired_pair(text, call),
    }


def _paired_pair(text: str, call: dict) -> dict:
    """The paired call and result in both the plain and the message shapes."""
    from langchain_core.messages import AIMessage, ToolMessage

    return {
        "tool_calls": [call],
        "tool_results": [_paired_tool_result(text, call)],
        "messages": [
            AIMessage(content="", tool_calls=[call]),
            ToolMessage(content=text, name=call["name"], tool_call_id=call["id"]),
        ],
    }


def _record_or_receipt(result) -> dict:
    """The single evidence-like record the collector returns."""
    assert result is not None, "the collector returned nothing for a usable snapshot"
    if isinstance(result, dict) and "record" in result:
        return result["record"]
    assert isinstance(result, dict), f"unexpected collector result: {type(result).__name__}"
    return result


def _records(result) -> list[dict]:
    if result is None:
        return []
    if isinstance(result, dict):
        if "records" in result:
            return list(result["records"])
        return [result]
    return list(result)


# --- positive: the window and the retained material ---------------------------


def _run_config(tmp_path) -> dict:
    """An isolated run config: no shared cache, no shared results."""
    from tradingagents.default_config import DEFAULT_CONFIG

    config = dict(DEFAULT_CONFIG)
    config.update({
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
    })
    return config


@pytest.mark.unit
def test_fixed_frame_matches_the_ohlcv_column_layout():
    """The fixture has the columns ``load_ohlcv`` produces, one row per session."""
    frame = _fixed_frame()
    assert list(frame.columns) == ["Date", "Open", "High", "Low", "Close", "Volume"]
    assert len(frame) == len(FIXED_ROWS)
    assert list(frame["Date"]) == [row[0] for row in FIXED_ROWS]
    assert frame["Date"].iloc[-1] == TRADE_DATE


@pytest.mark.unit
def test_real_snapshot_renders_recent_closes_table(monkeypatch, tmp_path):
    """The real ``@tool`` over the fixed OHLCV frame yields the frozen table."""
    from tradingagents.dataflows.config import run_config

    with run_config(_run_config(tmp_path)):
        _pin_ohlcv(monkeypatch)
        text = _snapshot_text(look_back_days=7)

    rows = _recent_rows(text)
    assert rows == [(date, _price(close)) for date, _o, _h, _l, close, _v in FIXED_ROWS], rows
    assert LATEST_CLOSE in text
    assert "## Verified market data snapshot for AAPL" in text


@pytest.mark.unit
def test_tool_node_injects_symbol_and_trade_date_from_state(monkeypatch, tmp_path):
    """The real ``ToolNode`` injects ``symbol``/``trade_date``; the model passes neither.

    This is the path the analyst subgraph uses: the model's ``tool_calls`` carry
    only ``curr_date`` and ``look_back_days``, and the node fills the injected
    arguments from the run state. The node runs inside a compiled graph, because
    that is where the graph runtime supplies the state ``InjectedState`` reads; a
    bare ``ToolNode.invoke`` never reaches the tool.
    """
    _import_graph_entry()
    from langchain_core.messages import AIMessage

    from tradingagents.agents.analysts.market_analyst import TOOLS
    from tradingagents.dataflows.config import run_config

    call = {"name": TOOL_NAME, "args": _paired_call()["args"], "id": "call-node"}
    with run_config(_run_config(tmp_path)):
        calls = _pin_ohlcv(monkeypatch)
        out = _tool_graph(TOOLS).invoke({
            **_graph_state(),
            "messages": [AIMessage(content="", tool_calls=[call])],
        })

    tool_messages = [m for m in out["messages"] if getattr(m, "tool_call_id", None) == "call-node"]
    assert len(tool_messages) == 1, f"the node ran {len(tool_messages)} tools for one call"
    text = tool_messages[0].content
    assert SNAPSHOT_HEADING in text, f"the node did not return a snapshot: {text!r}"
    assert _recent_rows(text)[-1] == (TRADE_DATE, LATEST_CLOSE)
    # The injected symbol reached the vendor call, not the model's args.
    assert [c[0] for c in calls] == [TICKER], calls
    assert [c[1] for c in calls] == [TRADE_DATE], calls


@pytest.mark.unit
def test_snapshot_window_is_clamped_to_look_back_days(monkeypatch, tmp_path):
    """W-A row bound: ``max(1, min(int(look_back_days), 30))``, at least one row."""
    from tradingagents.dataflows.config import run_config

    with run_config(_run_config(tmp_path)):
        _pin_ohlcv(monkeypatch)
        two_rows = _recent_rows(_snapshot_text(look_back_days=2))
        capped = _recent_rows(_snapshot_text(look_back_days=99))
        zero_rows = _recent_rows(_snapshot_text(look_back_days=0))

    assert len(two_rows) == 2
    assert [r[0] for r in two_rows] == [r[0] for r in FIXED_ROWS[-2:]]
    assert len(capped) <= 30
    assert len(capped) == len(FIXED_ROWS)
    assert len(zero_rows) == 1, "a look-back of 0 must still show one row"


@pytest.mark.unit
def test_collector_creates_one_record_with_window_and_retained_material(monkeypatch, tmp_path):
    """W-A + §4: one record, window from the shown rows, ``content_ref`` resolvable."""
    _require_collector()
    from tradingagents.dataflows.config import run_config

    results_dir = tmp_path / "results"
    with run_config(_run_config(tmp_path)):
        _pin_ohlcv(monkeypatch)
        text = _snapshot_text(look_back_days=7)
        result = _collect(
            _paired_call(), text, _paired_state(text), _run_context(RUN_A), results_dir,
        )

    record = _record_or_receipt(result)
    rows = _recent_rows(text)

    # Identity is copied from the RunContext, never derived from the ID spelling.
    assert record["run_id"] == RUN_A
    assert record["ticker"] == TICKER
    assert record["as_of_date"] == TRADE_DATE
    assert record["contract_version"] == CONTRACT_VERSION

    # Window W-A (note §3.2) is computed from the dates the snapshot shows, and
    # the snapshot's dates are the fixed frame's.
    assert rows and rows[-1][0] == TRADE_DATE
    assert record["window_start"] == rows[0][0]
    assert record["window_end"] == rows[-1][0]
    assert record["window_start"] <= record["window_end"]
    assert record["window_end"] <= TRADE_DATE
    assert len(rows) <= max(1, min(7, 30))

    # §3.3 source_ref locates the paired call and its effective arguments.
    assert "get_verified_market_snapshot" in record["source_ref"]
    assert "call-1" in record["source_ref"]
    assert TRADE_DATE in record["source_ref"]
    assert "look_back_days=7" in (record["source_ref"] or "")

    # §4.3 content_ref resolves to retained material under the run's root.
    assert record["content_ref"].startswith(f"evidence://{RUN_A}/")
    retained = _retained_files(results_dir)
    assert retained, "the collector retained no material for a usable snapshot"
    named = record["content_ref"].rsplit("/", 1)[-1]
    assert any(p.name == named for p in retained), (
        f"content_ref names {named!r}, which the run did not retain: {[p.name for p in retained]}"
    )
    material = "\n".join(p.read_text(encoding="utf-8") for p in retained)
    assert SNAPSHOT_HEADING in material
    assert LATEST_CLOSE in material


@pytest.mark.unit
def test_tool_clamps_a_future_curr_date_to_the_trade_date(monkeypatch, tmp_path):
    """``date_window.as_of``: a model asking for a later date gets no later row."""
    from tradingagents.dataflows.config import run_config

    with run_config(_run_config(tmp_path)):
        # The stale-frame guard would refuse a frame whose latest row is far from
        # the requested date, which is a different concern; the clamp is what is
        # under test here, so ``load_ohlcv`` is already replaced by ``_pin_ohlcv``.
        calls = _pin_ohlcv(monkeypatch)
        text = _snapshot_text(curr_date="2026-12-31", look_back_days=7)

    assert [c[1] for c in calls] == [TRADE_DATE], calls
    assert _recent_rows(text)[-1][0] == TRADE_DATE
    assert "2026-12-31" not in text


@pytest.mark.unit
def test_past_curr_date_is_served_as_requested(monkeypatch, tmp_path):
    """The clamp only bounds the future: an earlier model date is served as-is."""
    from tradingagents.dataflows.config import run_config

    with run_config(_run_config(tmp_path)):
        calls = _pin_ohlcv(monkeypatch)
        text = _snapshot_text(curr_date="2026-11-06", look_back_days=7)

    assert [c[1] for c in calls] == ["2026-11-06"], calls
    assert _recent_rows(text)[-1][0] == "2026-11-06"


def _retained_files(results_dir: Path, run_id: str = RUN_A) -> list[Path]:
    """Retained material for ``run_id`` under the §4.3 retention root."""
    root = results_dir / TICKER / TRADE_DATE / "evidence" / run_id
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file())


# --- wrap_up -------------------------------------------------------------------


def _wheel_model(report: str):
    """A fake model whose two branches ``take_turn`` can pipe its prompt into.

    ``take_turn`` does ``(prompt | llm.bind_tools(tools)).invoke(messages)`` on a
    tool turn and ``(prompt | llm).invoke(_as_text(messages))`` on the wrap-up
    turn, so both branches receive a ``PromptValue`` from the pipe, not a list.
    Each branch is therefore a real ``Runnable``: the bound one is a
    ``RunnableLambda`` that emits the snapshot ``tool_calls``, and the plain one a
    ``RunnableLambda`` that produces the report. Both convert the prompt to a
    message list before inspecting it.

    The bound branch also recognises the wrap-up history: ``take_turn`` only
    skips binding when the last human message is ``WRAP_UP``, but a wiring that
    bound tools anyway must still end, so a bound turn holding ``WRAP_UP`` answers
    with the report instead of calling the tool again. That is what leaves the run
    with two tool results and one closing report.
    """
    _import_graph_entry()
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.runnables import RunnableLambda

    from tradingagents.agents.analysts.turn import WRAP_UP

    def _as_messages(prompt) -> list:
        """The prompt as a message list, whichever form the caller passed."""
        to_messages = getattr(prompt, "to_messages", None)
        return to_messages() if callable(to_messages) else list(prompt)

    def _is_wrap_up(messages) -> bool:
        return (
            bool(messages)
            and isinstance(messages[-1], HumanMessage)
            and messages[-1].content == WRAP_UP
        )

    class _Model:
        def __init__(self):
            self.bound_calls = 0
            self.plain_calls = 0
            self.turns: list[dict] = []
            self.wrap_up_seen: list[str] = []

        def _snapshots(self, messages) -> list[str]:
            return [
                text for text in (getattr(m, "content", "") for m in messages)
                if isinstance(text, str) and SNAPSHOT_HEADING in text
            ]

        def _tool_turn(self, prompt):
            self.bound_calls += 1
            messages = _as_messages(prompt)
            if _is_wrap_up(messages):
                # Bound but told the rounds are spent: answer, don't call again.
                self.turns.append({"wrap_up": True, "tools_bound": True})
                self.wrap_up_seen = self._snapshots(messages)
                return AIMessage(content=report)
            n = self.bound_calls
            self.turns.append({"wrap_up": False, "tools_bound": True})
            return AIMessage(content="", tool_calls=[{
                "name": TOOL_NAME,
                "args": _paired_call(call_id=f"call-{n}")["args"],
                "id": f"call-{n}",
            }])

        def _plain_turn(self, prompt):
            self.plain_calls += 1
            messages = _as_messages(prompt)
            wrapped = _is_wrap_up(messages)
            self.turns.append({"wrap_up": wrapped, "tools_bound": False})
            if wrapped:
                self.wrap_up_seen = self._snapshots(messages)
            return AIMessage(content=report)

        def bind_tools(self, tools, **kwargs):
            return RunnableLambda(self._tool_turn)

        def invoke(self, prompt):
            return self._plain_turn(prompt)

    return _Model()


@pytest.mark.unit
def test_wrap_up_subgraph_calls_the_real_tool_then_writes_the_report(monkeypatch, tmp_path):
    """R8-B §6 A-10: the analyst subgraph runs real tool rounds, then wraps up.

    The model calls the snapshot tool every round until ``max_tool_rounds`` is
    spent on the **production** analyst subgraph (``setup._analyst_graph``); its
    real ``ToolNode`` injects ``symbol``/``trade_date``, so each round renders the
    fixed frame. The production wrap-up turn then appends ``WRAP_UP`` and asks for
    the report; the fake model answers it with the report instead of calling a
    third tool, so the run ends with two tool results and one closing turn that
    saw both of them.
    """
    from tradingagents.dataflows.config import run_config

    max_tool_rounds = 2
    report = f"AAPL closed at {LATEST_CLOSE} USD on {TRADE_DATE}."

    with run_config(_run_config(tmp_path)):
        calls = _pin_ohlcv(monkeypatch)
        model = _wheel_model(report)
        subgraph, marker = _market_analyst_subgraph(model, max_tool_rounds)
        out = subgraph.invoke({
            **_graph_state(),
            "messages": [("human", TICKER)],
        })

    # The real tool ran in the real subgraph for every round, against the fixed frame.
    assert model.bound_calls == max_tool_rounds, (
        f"expected {max_tool_rounds} tool-bound turns, got {model.bound_calls}"
    )
    assert marker.bound_turns == max_tool_rounds
    assert len(calls) == max_tool_rounds, f"tools executed: {calls}"
    assert {c[0] for c in calls} == {TICKER}
    assert {c[1] for c in calls} == {TRADE_DATE}
    assert {c[2] for c in calls} == {False}, (
        f"the snapshot must read the raw session rows (fill_gaps=False): {calls}"
    )

    # Two tool rounds, then exactly one closing turn on the production wrap-up
    # history; the fake model does not call a third tool when it is wrapped up.
    assert model.turns == [
        {"wrap_up": False, "tools_bound": True},
        {"wrap_up": False, "tools_bound": True},
        {"wrap_up": True, "tools_bound": False},
    ], f"unexpected turn sequence: {model.turns}"
    assert marker.turns == model.turns, (
        f"the production wiring's turn sequence differs from the model's: {marker.turns}"
    )
    assert model.plain_calls == 1, "the wrap-up turn must be the only unbound call"
    assert out["market_report"] == report

    # The closing turn saw both tool results, each carrying the verified snapshot.
    assert len(model.wrap_up_seen) == max_tool_rounds, (
        f"the wrap-up turn saw {len(model.wrap_up_seen)} snapshot results, "
        f"expected {max_tool_rounds}"
    )
    for result in model.wrap_up_seen:
        assert _recent_rows(result)[-1] == (TRADE_DATE, LATEST_CLOSE)


@pytest.mark.unit
def test_subgraph_hands_retained_snapshots_up_as_market_evidence(monkeypatch, tmp_path):
    """R8-B §4: the market subgraph returns its retained receipts to the parent.

    The subgraph's tool calls and results never leave it, so it must retain the
    snapshots itself and expose them under ``market_evidence``; the Index Evidence
    step folds that key into the run's index. Without the key the parent graph
    would only ever see the report and the run could not cite verified data.
    """
    from tradingagents.dataflows.config import run_config

    max_tool_rounds = 2
    report = f"AAPL closed at {LATEST_CLOSE} USD on {TRADE_DATE}."

    with run_config(_run_config(tmp_path)):
        _pin_ohlcv(monkeypatch)
        model = _wheel_model(report)
        subgraph, _marker = _market_analyst_subgraph(model, max_tool_rounds)
        out = subgraph.invoke({
            **_graph_state(),
            "run_id": RUN_A,
            "messages": [("human", TICKER)],
        })

    receipts = out.get("market_evidence")
    assert receipts, (
        "the market subgraph returned no market_evidence: the parent graph cannot "
        f"index a snapshot the run really took (output keys: {sorted(out)})"
    )
    assert len(receipts) == max_tool_rounds, f"one receipt per tool round expected: {receipts}"
    for record in receipts:
        assert record["run_id"] == RUN_A
        assert record["ticker"] == TICKER
        assert record["as_of_date"] == TRADE_DATE
        assert record["source_kind"] == "market_snapshot"
        assert (record.get("content_ref") or "").startswith(f"evidence://{RUN_A}/")
        # The reference names material this run really retained.
        named = record["content_ref"].rsplit("/", 1)[-1]
        retained = _retained_files(Path(_run_config(tmp_path)["results_dir"]))
        assert any(p.name == named for p in retained), (
            f"content_ref names {named!r}, which the subgraph did not retain: "
            f"{[p.name for p in retained]}"
        )


# --- negative: placeholders and report-only runs -------------------------------


@pytest.mark.unit
def test_vendor_unavailable_placeholder_creates_no_record(monkeypatch, tmp_path):
    """An error placeholder is not substantive evidence (C1): no record is built.

    The placeholder text is what the tool actually returns for a vendor failure;
    it is reproduced here by driving the real tool with a failing ``load_ohlcv``,
    not by guessing the router's wording.
    """
    _require_collector()
    import tradingagents.dataflows.vendors.yahoo.snapshot as snapshot

    from tradingagents.dataflows.config import run_config
    from tradingagents.dataflows.errors import VendorUnavailableError

    def _fail(symbol, as_of_date, fill_gaps=True):
        raise VendorUnavailableError("yahoo", "rate limited")

    results_dir = tmp_path / "results"
    with run_config(_run_config(tmp_path)):
        monkeypatch.setattr(snapshot, "load_ohlcv", _fail)
        placeholder = _snapshot_text(look_back_days=7)

        result = _collect(
            _paired_call("call-err"), placeholder, _paired_state(placeholder, _paired_call("call-err")),
            _run_context(RUN_A), results_dir,
        )

    assert _records(result) == [], f"an error placeholder must not become evidence: {placeholder!r}"
    # No material is retained for a response that carried no snapshot (the
    # placeholder text itself is returned by the real tool over the failing frame).
    retained = _retained_files(results_dir)
    assert not retained, f"a placeholder retained market material: {retained}"


@pytest.mark.unit
def test_no_market_data_placeholder_creates_no_record(monkeypatch, tmp_path):
    """A "no data" placeholder is also absent evidence, not a positive snapshot."""
    _require_collector()
    import tradingagents.dataflows.vendors.yahoo.snapshot as snapshot

    from tradingagents.dataflows.config import run_config
    from tradingagents.dataflows.errors import NoMarketDataError

    def _empty(symbol, as_of_date, fill_gaps=True):
        raise NoMarketDataError(symbol, None, "no price rows")

    results_dir = tmp_path / "results"
    with run_config(_run_config(tmp_path)):
        monkeypatch.setattr(snapshot, "load_ohlcv", _empty)
        placeholder = _snapshot_text(look_back_days=7)

        result = _collect(
            _paired_call("call-empty"), placeholder,
            _paired_state(placeholder, _paired_call("call-empty")),
            _run_context(RUN_A), results_dir,
        )
    assert _records(result) == [], f"a no-data placeholder must not become evidence: {placeholder!r}"
    assert not _retained_files(results_dir), "a no-data response retained market material"


@pytest.mark.unit
def test_report_only_run_has_no_snapshot_evidence(monkeypatch, tmp_path):
    """A run whose analyst only wrote a report must not gain a snapshot record.

    No ``get_verified_market_snapshot`` call is paired in this run's messages, so
    there is nothing for the collector to bind a record to.
    """
    _require_collector()
    report = "AAPL trended up; I did not check the verified snapshot."
    state = {**_graph_state(), "market_report": report, "messages": []}
    result = _collect({}, "", state, _run_context(RUN_A), tmp_path / "results")
    assert _records(result) == []


# --- negative: retained material and cross-run --------------------------------


@pytest.mark.unit
def test_unreadable_retained_material_creates_no_record(monkeypatch, tmp_path):
    """§4.3: material that cannot be read back is not evidence.

    A usable snapshot must first mint a record that resolves — otherwise the
    "refuse everything" collector would pass the case vacuously. Only then is the
    retained material deleted, and the later collect may not claim it back.
    """
    _require_collector()
    from tradingagents.dataflows.config import run_config

    results_dir = tmp_path / "results"
    with run_config(_run_config(tmp_path)):
        _pin_ohlcv(monkeypatch)
        text = _snapshot_text(look_back_days=7)

    # A usable snapshot must produce a record: the positive control for the case.
    first = _collect(_paired_call(), text, _paired_state(text), _run_context(RUN_A), results_dir)
    assert _records(first), (
        "a usable snapshot minted no record, so the loss rule below would pass "
        f"vacuously; collector returned {first!r}"
    )
    record = _record_or_receipt(first)
    ref = record.get("content_ref") or ""
    assert ref, f"the collector returned a record with no content_ref: {record}"
    name = ref.rsplit("/", 1)[-1]
    victims = [p for p in _retained_files(results_dir) if p.name == name]
    assert victims, f"content_ref names material the run did not retain: {ref}"
    for path in victims:
        path.unlink()

    # A later collect of the same response must not mint a record it cannot read.
    result = _collect(_paired_call(), text, _paired_state(text), _run_context(RUN_A), results_dir)
    for candidate in _records(result):
        candidate_ref = candidate.get("content_ref") or ""
        candidate_name = candidate_ref.rsplit("/", 1)[-1]
        resolved = [p for p in _retained_files(results_dir) if p.name == candidate_name]
        assert resolved, (
            "a later record points at material that is no longer retained "
            f"(deleted {name!r}): {candidate_ref!r}"
        )
    if not _records(result):
        # Refusing is the other correct answer: nothing claims evidence it lacks.
        assert "content_ref" not in repr(result)


def _snapshot_evidence_of(result) -> list[dict]:
    """Every snapshot-evidence record in a collector result (other kinds are untouched)."""
    kind_keys = ("evidence_kind", "kind", "source_kind")
    found = []
    for record in _records(result):
        if any(record.get(k) == "market_snapshot" for k in kind_keys):
            found.append(record)
    return found


@pytest.mark.unit
def test_foreign_run_evidence_is_not_resolvable(monkeypatch, tmp_path):
    """C0: a record minted for run A is not evidence for run B.

    The same tool response is collected twice and only the RunContext's
    ``run_id`` changes. Run A's record stays run A's; any record run B mints
    carries run B's identity and lives under run B's own retention root. The
    same-response positive control follows below.
    """
    _require_collector()
    from tradingagents.dataflows.config import run_config

    results_dir = tmp_path / "results"
    with run_config(_run_config(tmp_path)):
        _pin_ohlcv(monkeypatch)
        text = _snapshot_text(look_back_days=7)
        run_a = _record_or_receipt(
            _collect(_paired_call(), text, _paired_state(text), _run_context(RUN_A), results_dir)
        )
        # The same tool response presented under run B must not reuse run A's record.
        run_b_result = _collect(
            _paired_call(), text, _paired_state(text), _run_context(RUN_B), results_dir,
        )

    assert run_a["run_id"] == RUN_A
    # Run B's snapshot material, if any, belongs to run B and lives under its own
    # retention root: a record it re-attributes to run A is the failure under test.
    for record in _snapshot_evidence_of(run_b_result):
        assert record["run_id"] == RUN_B, "a foreign run's record was reattributed"
        assert record.get("evidence_id") != run_a.get("evidence_id")
        assert (record.get("content_ref") or "").startswith(f"evidence://{RUN_B}/")
    # Run A's retained material is untouched by run B's reads.
    assert _retained_files(results_dir, RUN_A), "run B consumed or removed run A's material"


@pytest.mark.unit
def test_two_runs_collecting_the_same_response_get_distinct_evidence(monkeypatch, tmp_path):
    """C0 §1: the same tool response under two RunContexts is two separate records.

    The positive control for the cross-run negative above: the response is
    identical, so a difference between the two records can only come from the
    run identity, which is what keeps evidence scoped to its run.
    """
    _require_collector()
    from tradingagents.dataflows.config import run_config

    results_dir = tmp_path / "results"
    with run_config(_run_config(tmp_path)):
        _pin_ohlcv(monkeypatch)
        text = _snapshot_text(look_back_days=7)
        a = _record_or_receipt(
            _collect(_paired_call(), text, _paired_state(text), _run_context(RUN_A), results_dir)
        )
        b = _record_or_receipt(
            _collect(_paired_call(), text, _paired_state(text), _run_context(RUN_B), results_dir)
        )

    assert (a["run_id"], b["run_id"]) == (RUN_A, RUN_B)
    assert a["evidence_id"] != b["evidence_id"]
    assert a["content_ref"] != b["content_ref"]
    for record in (a, b):
        assert record["ticker"] == TICKER
        assert record["as_of_date"] == TRADE_DATE
        assert record["contract_version"] == CONTRACT_VERSION
    assert _retained_files(results_dir, RUN_A), "run A retained no material"
    assert _retained_files(results_dir, RUN_B), "run B retained no material"
