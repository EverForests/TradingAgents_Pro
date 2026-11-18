import hashlib
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import tradingagents
from tradingagents.agents.context import build_instrument_context, resolve_instrument_identity
from tradingagents.agents.rating import run_rating
from tradingagents.dataflows.config import run_config, run_config_context, set_config
from tradingagents.dataflows.date_window import get_current_date, is_historical
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients import create_tier_client, tier_provider
from tradingagents.llm_clients.budget_transport import request_budget_scope, terminal_request_status
from tradingagents.llm_clients.request_budget import RequestBudget
from tradingagents.memory import TradingMemoryLog, settlement
from tradingagents.memory.reflection import Reflector
from tradingagents.reporting import write_report_tree

from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .propagation import Propagator
from .setup import GraphSetup

logger = logging.getLogger(__name__)


def _validate_trade_date(trade_date) -> str:
    """The run date as a canonical ``YYYY-MM-DD`` string no later than today."""
    value = str(trade_date)
    try:
        canonical = datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") == value
    except ValueError:
        canonical = False
    if not canonical:
        raise ValueError(f"trade_date must be a date in YYYY-MM-DD format, got {trade_date!r}")
    if value > get_current_date():
        raise ValueError(f"trade_date cannot be in the future: {value}")
    return value


# Config keys that do not change what a run writes: where it keeps its files,
# whether it checkpoints, and how often it retries a provider.
_NOT_IN_SIGNATURE = frozenset({
    "results_dir", "data_cache_dir", "memory_log_path", "checkpoint_enabled", "llm_max_retries",
})


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=("market", "social", "news", "fundamentals"),
        debug=False,
        config: dict[str, Any] = None,
        callbacks: list | None = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []

        set_config(self.config)

        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        extra = {"callbacks": self.callbacks} if self.callbacks else {}
        self.deep_thinking_llm = create_tier_client(self.config, "deep", **extra).get_llm()
        self.quick_thinking_llm = create_tier_client(self.config, "quick", **extra).get_llm()

        self.memory_log = TradingMemoryLog(self.config)

        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        # An analyst takes two graph steps per tool round, plus its first turn
        # and its wrap-up; a limit past the recursion limit would end the run
        # there instead.
        max_tool_rounds, max_recur_limit = self.config["max_tool_rounds"], self.config["max_recur_limit"]
        if 2 * max_tool_rounds + 2 >= max_recur_limit:
            raise ValueError(
                f"max_tool_rounds={max_tool_rounds} needs max_recur_limit above {2 * max_tool_rounds + 2}"
            )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.conditional_logic,
            max_tool_rounds,
        )

        self.propagator = Propagator(
            max_recur_limit=max_recur_limit,
        )
        self.reflector = Reflector(self.quick_thinking_llm)

        # Graph-shape-affecting run choices, kept for the checkpoint signature.
        self.selected_analysts = tuple(selected_analysts)

        # Set up the graph: keep the workflow for recompilation with a checkpointer.
        self.workflow = self.graph_setup.setup_graph(selected_analysts, memory_node=self._memory_step)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None
        self._resuming = False

    def resolve_instrument_context(self, ticker: str, asset_type: str = "stock",
                                   trade_date: str | None = None) -> str:
        """Resolve ticker identity once and return the full instrument context.

        Deterministic yfinance lookup (cached, fail-open) injected into a
        context string so every agent anchors to the real company instead of
        hallucinating one from the price chart (#814). Both the propagate()
        path and the CLI call this so the resolved identity reaches the whole
        graph regardless of entry point.
        """
        identity = resolve_instrument_identity(ticker)
        return build_instrument_context(ticker, asset_type, identity, trade_date)

    def _memory_as_of(self, trade_date) -> str | None:
        """Point-in-time cutoff for past-context lessons (#1251).

        A historical/backtest run (trade date before today) filters lessons to
        those already resolved by the trade date. A current-date run returns
        None, disabling the filter so live behavior and pre-migration entries
        (which have no stored resolution date) are unaffected.
        """
        return str(trade_date) if is_historical(trade_date) else None

    def _run_signature(self, asset_type: str, portfolio=None) -> str:
        """Run inputs that must invalidate a checkpoint if changed.

        Keyed into the checkpoint thread ID so a resume under a different analyst
        selection, debate/risk depth, or asset mode starts fresh instead of
        silently continuing the previous graph (#1089). The rest of the config
        counts too (provider, models, endpoint, language, vendors, limits): a
        resume must not carry reports that other settings produced. Only where
        the run keeps its files and how it retries are left out.
        """
        settings = {k: v for k, v in self.config.items() if k not in _NOT_IN_SIGNATURE}
        digest = hashlib.sha256(json.dumps(settings, sort_keys=True, default=str).encode()).hexdigest()[:12]
        return "|".join([
            "analysts=" + ",".join(self.selected_analysts),
            f"debate={self.config['max_debate_rounds']}",
            f"risk={self.config['max_risk_discuss_rounds']}",
            f"asset={asset_type}",
            # None, an empty book and a changed book are three different runs.
            f"portfolio={portfolio.fingerprint() if portfolio is not None else 'none'}",
            # The layout itself: a checkpoint saved when analysts ran one after
            # another has pending nodes this graph no longer has, and one saved
            # before the Memory Log step would resume without the lessons.
            "analysts=parallel",
            "memory=parallel",
            f"settings={digest}",
        ])

    def propagate(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        """Run the trading agents graph for a company on a specific date.

        ``asset_type`` selects between the stock pipeline (default) and the
        crypto pipeline (``"crypto"``) shipped in #567 — the CLI auto-detects
        from the ticker; programmatic callers pass it explicitly. When
        ``checkpoint_enabled`` is set in config, the graph is recompiled with
        a per-ticker SqliteSaver so a crashed run can resume from the last
        successful node on a subsequent invocation with the same ticker+date.

        Returns ``(final_state, signal)`` where ``signal`` is one of the 5-tier
        ratings (Buy / Overweight / Hold / Underweight / Sell) or ``"REVIEW"``
        when the decision had no parseable rating (#1170); guard with
        ``tradingagents.agents.rating.is_review`` before mapping it to the
        PortfolioRating enum.
        """
        trade_date = _validate_trade_date(trade_date)

        with run_config(self.config), \
                self.checkpoint_scope(company_name, trade_date, asset_type, portfolio) as thread_id_value:
            return self._run_graph(
                company_name, trade_date, asset_type=asset_type,
                checkpoint_thread_id=thread_id_value, portfolio=portfolio,
            )

    def begin_checkpoint(self, company_name, trade_date, asset_type: str = "stock", portfolio=None) -> str | None:
        """Recompile the graph with a per-ticker checkpointer and return the
        ``thread_id`` to inject into the stream/invoke ``config`` (or ``None``
        when checkpointing is disabled).

        Pair every call with :meth:`end_checkpoint` in a ``finally``. Both
        ``propagate`` (via :meth:`checkpoint_scope`) and the CLI stream path use
        this so ``--checkpoint`` actually resumes (#1249); previously the setup
        lived only inside ``propagate`` and the CLI streamed the checkpointer-less
        graph, making the flag a no-op.
        """
        self._resuming = False
        if not self.config.get("checkpoint_enabled"):
            return None
        signature = self._run_signature(asset_type, portfolio)
        self._checkpointer_ctx = get_checkpointer(self.config["data_cache_dir"], company_name)
        saver = self._checkpointer_ctx.__enter__()
        self.graph = self.workflow.compile(checkpointer=saver)

        step = checkpoint_step(
            self.config["data_cache_dir"], company_name, str(trade_date), signature
        )
        self._resuming = step is not None
        if step is not None:
            logger.info("Resuming from step %d for %s on %s", step, company_name, trade_date)
        else:
            logger.info("Starting fresh for %s on %s", company_name, trade_date)
        return thread_id(company_name, str(trade_date), signature)

    def checkpoint_input(self, init_state):
        """The value to stream/invoke: ``None`` to resume an existing checkpoint,
        else the initial state for a fresh run.

        LangGraph resumes an interrupted thread when invoked with ``None``;
        re-passing the initial state instead appends it through the message
        reducer, duplicating messages in the resumed state (#1249).
        """
        return None if self._resuming else init_state

    def end_checkpoint(self):
        """Restore the plain uncheckpointed graph after a checkpointed run."""
        if self._checkpointer_ctx is not None:
            self._checkpointer_ctx.__exit__(None, None, None)
            self._checkpointer_ctx = None
            self.graph = self.workflow.compile()
        self._resuming = False

    @contextmanager
    def checkpoint_scope(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        """Context-manager form of begin/end_checkpoint for the propagate path."""
        try:
            yield self.begin_checkpoint(company_name, trade_date, asset_type, portfolio)
        finally:
            self.end_checkpoint()

    def clear_checkpoint_on_success(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        """Drop a completed run's checkpoint so a later run starts fresh (#1249)."""
        if self.config.get("checkpoint_enabled"):
            clear_checkpoint(
                self.config["data_cache_dir"], company_name, str(trade_date),
                self._run_signature(asset_type, portfolio),
            )

    def run_settings(self) -> dict:
        """What produces this graph's runs, for the saved report and state log.

        An allowlist: endpoints (a backend_url can carry credentials), keys and
        local paths are never recorded.
        """
        cfg = self.config
        return {
            "version": tradingagents.__version__,
            "llm_provider": cfg.get("llm_provider"),
            "deep_think_provider": tier_provider(cfg, "deep") if cfg.get("llm_provider") else None,
            "deep_think_llm": cfg.get("deep_think_llm"),
            "quick_think_provider": tier_provider(cfg, "quick") if cfg.get("llm_provider") else None,
            "quick_think_llm": cfg.get("quick_think_llm"),
            "analysts": list(self.selected_analysts),
            "max_debate_rounds": cfg.get("max_debate_rounds"),
            "max_risk_discuss_rounds": cfg.get("max_risk_discuss_rounds"),
            "output_language": cfg.get("output_language"),
            "data_vendors": dict(cfg.get("data_vendors") or {}),
            "tool_vendors": dict(cfg.get("tool_vendors") or {}),
        }

    def save_reports(self, final_state, ticker, save_path=None, html=True) -> Path:
        """Write the report tree for a completed run, like the CLI does.

        Programmatic callers get the same on-disk reports the CLI produces. Pass
        an explicit ``save_path`` or let it default under ``results_dir``; the
        report is also written as one HTML page unless ``html`` is False.

        FR-01 / INV-01: an official report is written only from the publication
        gate's own ``publication_result``. A state that never passed the gate — no
        result, or only a flat ``publication_status`` someone set — raises
        ``PublicationRequiredError`` and writes nothing, so a candidate can never
        be saved as an official decision. A real BLOCKED result still writes a
        diagnostic report: the same tree without an official rating, without the
        candidate body and without ``5_portfolio/decision.md``.
        """
        from tradingagents.graph.publication_gate import (
            PublicationRequiredError,
            publication_result_from_state,
        )

        result = publication_result_from_state(final_state)
        if result is None:
            raise PublicationRequiredError(
                "save_reports() needs the publication gate's publication_result; this "
                "state has none (a flat publication_status is not a gate result), so no "
                "official report was written"
            )
        if save_path is None:
            save_path = self.default_report_path(ticker)
        return write_report_tree(
            final_state, ticker, save_path, settings=self.run_settings(), html=html,
        )

    def default_report_path(self, ticker) -> Path:
        """Where a run's reports go unless told otherwise: under results_dir, stamped now."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return Path(self.config["results_dir"]) / "reports" / f"{safe_ticker_component(ticker)}_{stamp}"

    def create_run_state(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        """Build a run's initial state; propagate() and the CLI both start here.

        Injects the resolved instrument identity for every agent (#814). The
        memory log's lessons are not here: the graph's Memory Log step settles
        and loads them alongside the analysts (see ``_memory_step``).
        """
        trade_date = _validate_trade_date(trade_date)
        # The initial state mints this run's one ``course_run`` identity, so the
        # propagator call must read this graph's config on every entry path
        # (propagate(), the CLI stream, a bare create_run_state()): inside its own
        # ``run_config`` block the identity no longer depends on whatever happened
        # to be serving config at call time. Nested blocks restore the outer one on
        # exit, so propagating callers see the config they set.
        with run_config(self.config):
            return self.propagator.create_initial_state(
                company_name,
                trade_date,
                asset_type=asset_type,
                instrument_context=self.resolve_instrument_context(company_name, asset_type, trade_date),
                portfolio_context=portfolio.render(company_name) if portfolio is not None else "",
            )

    def _run_budget(self, init_agent_state) -> RequestBudget | None:
        """The metered budget for this run, or ``None`` when metering is off.

        One ``RequestBudget`` per main analysis flow (NFR-01 / INV-02, C4), keyed
        by the run identity the initial state already minted, with the limit
        recorded on its ``course_run``. ``None`` outside ``request_budget_enabled``
        (no budget is fabricated). Under it, a run with no usable identity refuses
        rather than running unlimited: a missing or malformed ``course_run`` raises
        ``ValueError``, and :class:`RequestBudget` refuses a missing or non-positive
        limit.
        """
        if not self.config.get("request_budget_enabled"):
            return None
        course_run = init_agent_state.get("course_run") if isinstance(init_agent_state, dict) else None
        if not isinstance(course_run, dict):
            raise ValueError(
                "request metering is enabled but the initial state carries no course_run; "
                "refusing to run unmetered"
            )
        return RequestBudget(course_run.get("run_id"), course_run.get("request_limit"))

    def _terminal_state(self, graph_input, init_agent_state, exc: BaseException, latest=None) -> dict | None:
        """The one final state of a run that ended on a recognized C4/C5 failure.

        Built from ``init_agent_state`` — so a resumed run that streamed ``None``
        still has the identity the gate needs — then overlaid with whatever the run
        had produced (``latest``) and the terminal C0 code in the flat
        ``execution_status`` and on its ``course_run``. ``None`` when the failure is
        not a recognized budget/context/provider refusal: the caller re-raises.
        """
        if latest is None:
            latest = graph_input if graph_input is not None else init_agent_state
        terminal = terminal_request_status(exc)
        if terminal is None:
            return None
        # Actual latest values win over the initial state; a partial state never
        # removes an identity field it did not see.
        final_state = {}
        for source in (init_agent_state, latest):
            if isinstance(source, dict):
                final_state.update(source)
        final_state["execution_status"] = terminal
        course_run = final_state.get("course_run")
        if isinstance(course_run, dict):
            final_state["course_run"] = {**course_run, "execution_status": terminal}
        return final_state

    def _memory_step(self, state):
        """The graph's Memory Log step, alongside the analysts (#1428): settle every
        ticker's due decisions (#1445), then return the lessons known by the
        trade date for the Portfolio Manager (#1251).

        Settling fetches prices and asks the model for a reflection per decision,
        so it runs beside the analysts instead of before them. A failure here
        does not end the run: the analysts' work is kept, the lessons already in
        the log are used, and the report says what could not be settled.
        """
        note = ""
        try:
            # Settlement and reflection are historical work, not part of the run's
            # model flow (NFR-01 / INV-02, C4): their requests are made outside the
            # run's budget scope, so they never consume a slot from it. An explicit
            # ``None`` scope keeps that true even when a caller has one published.
            with request_budget_scope(None):
                # Another run settling the same log does the work; this one goes on.
                done = self.settle_all_pending(wait=False)
            if done.failed:
                note = (f"{len(done.failed)} past decision(s) could not be settled this run "
                        "and stay pending.")
        except Exception as exc:
            logger.warning("Settling past decisions failed: %s", exc)
            note = f"Past decisions could not be settled this run ({type(exc).__name__}); they stay pending."
        try:
            past_context = self.memory_log.get_past_context(
                state["company_of_interest"], as_of=self._memory_as_of(state["trade_date"]))
        except Exception as exc:
            logger.warning("Reading the memory log failed: %s", exc)
            past_context = ""
            note = note or f"The memory log could not be read this run ({type(exc).__name__})."
        return {"past_context": past_context, "memory_note": note}

    def settle_pending(self, company_name) -> settlement.Settlement:
        """Settle this ticker's decisions whose holding window has now traded.

        A run settles every due decision alongside its analysts, so its own
        decision stays pending until a later run. A caller that is done
        analyzing a ticker (a backtest sweep, a scheduled job) calls this to
        settle it now. Returns what was settled and what failed.
        """
        with run_config(self.config):
            return settlement.settle_pending(company_name, self.memory_log, self.reflector, self.config)

    def settle_all_pending(self, wait: bool = True) -> settlement.Settlement:
        """Settle every ticker's decisions whose holding window has now traded (#1445).

        For a scheduler whose tickers rotate: a ticker it stops analysing would
        otherwise keep its decisions pending, and their lessons out of later runs.
        With ``wait=False`` a pass already running on the same log is not waited for.
        """
        with run_config(self.config):
            return settlement.settle_all_pending(self.memory_log, self.reflector, self.config, wait=wait)

    def record_decision(self, company_name, trade_date, final_state):
        """Record a finished run: its state log, and its decision in the memory log
        for reflection on the next same-ticker run. propagate() and the CLI both end here.

        FR-01 / INV-01: a run the publication gate blocked writes nothing to
        decision memory — not a rating, not even a REVIEW entry — and its state log
        omits the candidate body.
        """
        self._log_state(trade_date, final_state)
        from tradingagents.graph.publication_gate import publication_result_from_state

        result = publication_result_from_state(final_state)
        if result is None or not result.approved:
            logger.warning(
                "Publication blocked for %s on %s (%s); nothing added to the memory log",
                company_name, trade_date,
                result.reason if result is not None else "no gate result",
            )
            return
        decision = final_state.get("final_trade_decision")
        if not decision:
            logger.warning("No final decision for %s on %s; nothing added to the memory log",
                           company_name, trade_date)
            return
        self.memory_log.store_decision(
            ticker=company_name, trade_date=trade_date, final_trade_decision=decision,
            rating=run_rating(final_state),
        )

    def _run_graph(self, company_name, trade_date, asset_type: str = "stock",
                   checkpoint_thread_id: str | None = None, portfolio=None):
        """Execute the graph and write the resulting state to disk and memory log."""
        init_agent_state = self.create_run_state(company_name, trade_date, asset_type, portfolio)
        args = self.propagator.get_graph_args()

        # Inject the checkpoint thread_id (from checkpoint_scope) so the same
        # ticker+date+graph-shape resumes; a different one starts fresh (#1089).
        if checkpoint_thread_id is not None:
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = checkpoint_thread_id

        # None resumes an existing checkpoint; init_agent_state starts fresh (#1249).
        graph_input = self.checkpoint_input(init_agent_state)
        if self.debug:
            # A state repeats the messages before it, so each prints once (#1027).
            final_state, printed = {}, set()
            for messages, state in self.stream_run(graph_input, **args):
                for msg in messages:
                    key = getattr(msg, "id", None) or (type(msg).__name__, getattr(msg, "content", None))
                    if key not in printed:
                        printed.add(key)
                        msg.pretty_print()
                if state is not None:
                    final_state.update(state)
        else:
            # NFR-01 / INV-02 (C4): one budget for this run, published for the
            # whole invoke so every outbound request of the flow is metered. A
            # recognized refusal ends the run with a terminal state instead of
            # propagating a half-finished graph — recording the terminal code on a
            # final state whose normal tail still runs (the gate then blocks it),
            # so the API and CLI end the same way; any other error re-raises.
            budget = self._run_budget(init_agent_state)
            try:
                with request_budget_scope(budget):
                    final_state = self.graph.invoke(graph_input, **args)
            except Exception as exc:
                terminal_state = self._terminal_state(graph_input, init_agent_state, exc)
                if terminal_state is None:
                    raise
                run_id = (init_agent_state.get("course_run") or {}).get("run_id")
                logger.warning(
                    "Run %s for %s on %s ended as %s",
                    run_id, company_name, trade_date, terminal_state["execution_status"],
                )
                final_state = terminal_state

        # The graph returned normally, so the run finished: only now does its
        # execution state become COMPLETED. A run that raised above never reaches
        # this line and stays RUNNING, which the gate refuses as RUN_NOT_COMPLETE.
        # complete_run() keeps a terminal code already recorded (C0).
        self.complete_run(final_state)

        self.publish(final_state)

        self.record_decision(company_name, trade_date, final_state)

        # Clear checkpoint on successful completion to avoid stale state. A run
        # that ended on a terminal failure keeps its checkpoint, as before.
        if final_state.get("execution_status") == "COMPLETED":
            self.clear_checkpoint_on_success(company_name, trade_date, asset_type, portfolio)

        return final_state, run_rating(final_state)

    def complete_run(self, final_state: dict) -> dict:
        """Mark a run that finished normally as ``COMPLETED`` (C0).

        The only place a run becomes ``COMPLETED``: ``_run_graph`` and the CLI
        call it after the graph returns normally, right before the gate judges the
        candidate. A terminal C0 failure already recorded — ``BUDGET_EXHAUSTED``,
        ``CONTEXT_TOO_LARGE`` or ``FAILED`` — keeps its own code and is never
        overwritten, and a state with no ``course_run`` stays without one, so the
        gate refuses it.
        """
        if not isinstance(final_state, dict):
            return final_state
        terminal = ("BUDGET_EXHAUSTED", "CONTEXT_TOO_LARGE", "FAILED")
        current = final_state.get("execution_status")
        if current in terminal:
            return final_state
        course_run = final_state.get("course_run")
        # A RunContext that already records a terminal failure is not upgraded
        # either, even when the flat field was not set.
        if isinstance(course_run, dict) and course_run.get("execution_status") in terminal:
            return final_state
        final_state["execution_status"] = "COMPLETED"
        if isinstance(course_run, dict):
            final_state["course_run"] = {**course_run, "execution_status": "COMPLETED"}
        return final_state

    def publish(self, final_state: dict) -> str:
        """FR-01 / INV-01: decide whether this run's candidate may publish.

        Single deterministic gate, called once per run before any sink reads it
        (CLI display, API return, report save, memory write). Verifies the chain
        recommendation -> accepted argument -> this run's retained material using
        the authoritative ID->record mappings (``argument_index`` /
        ``evidence_index``) and the run's ``course_run``; it never re-builds the
        index or accepts new arguments. A run the gate judges must have finished
        normally (``complete_run``); one still running, or with no ``RunContext``,
        is refused as ``RUN_NOT_COMPLETE``. Writes one ``publication_result`` onto
        ``final_state`` and returns the publication status.

        The Portfolio Manager writes only internal candidate fields; on refusal
        the candidate body and rating are removed and no official rating is set,
        so no official field carries them.
        """
        from tradingagents.graph.publication_gate import (
            apply_publication,
            evaluate_publication,
            publication_run,
        )

        run = publication_run(final_state)
        # A terminal C0 failure recorded on the state outranks the RunContext.
        if final_state.get("execution_status") and final_state.get("execution_status") != run.get("execution_status"):
            run = {**run, "execution_status": final_state["execution_status"]}
        evidence_index = final_state.get("evidence_index") or {}
        # The authoritative ID -> record mapping the researchers wrote. A state
        # with none has no accepted argument, so nothing can resolve.
        argument_index = final_state.get("argument_index") or {}
        result = evaluate_publication(
            {
                "rating": final_state.get("candidate_rating"),
                "argument_ids": final_state.get("candidate_argument_ids") or (),
            },
            argument_index,
            evidence_index,
            run,
            # The gate re-reads each record's retained material from this run's
            # retention root, so an expired or deleted reference cannot publish.
            results_dir=self.config.get("results_dir"),
        )
        apply_publication(result, final_state)
        return result.publication_status

    def stream_run(self, graph_input, **args):
        """Stream a run as ``(messages, state)`` pairs.

        ``messages`` are the agents' messages, the analysts' included. ``state``
        is the run's state after a top-level step; for a step inside an analyst's
        graph it is that analyst's report once filed, else None.

        Each analyst works in a graph of its own, and the run's state takes the
        analysts' reports only when the slowest has finished, so their messages
        and reports come from their own finished steps ("tasks") as they happen.

        NFR-01 / INV-02 (C4): one budget is built from the run's initial state and
        published inside the run's own context, so it covers every step of this
        flow and never leaks into the caller's context (restored across yields).
        A run that ends on a recognized C4/C5 refusal yields exactly one more
        state — the terminal state — instead of a traceback, so the debug path and
        the CLI consume the same final state as ``propagate()``.
        """
        # The initial state is this run's identity; ``None`` (a resume) carries no
        # usable budget, so the resume path keeps its existing behavior.
        init_agent_state = graph_input if isinstance(graph_input, dict) else {}
        args = {**args, "stream_mode": ["values", "tasks"]}
        # The graph's own config serves every tool call, as in propagate(), even
        # when the process-wide config has changed since. Each step runs in the
        # run's context, so the caller keeps its own between steps.
        context = run_config_context(self.config)
        # Copying before the scope captures the run's config but not a budget, so
        # this context starts with no active budget; only its own steps get one.
        budget = self._run_budget(init_agent_state)
        latest = init_agent_state or None

        def _begin():
            return request_budget_scope(budget)

        scope = context.run(_begin)
        context.run(scope.__enter__)
        try:
            stream = context.run(self.graph.stream, graph_input, subgraphs=True, **args)
            try:
                while (step := context.run(next, stream, None)) is not None:
                    namespace, mode, chunk = step
                    if namespace:
                        result = chunk.get("result") if mode == "tasks" else None
                        if isinstance(result, dict):
                            report = {k: v for k, v in result.items() if k != "messages" and v}
                            if result.get("messages") or report:
                                yield result.get("messages", []), report or None
                    elif mode == "values":
                        if isinstance(chunk, dict):
                            latest = chunk
                        yield chunk.get("messages", []), chunk
            except Exception as exc:
                terminal_state = self._terminal_state(graph_input, init_agent_state, exc, latest)
                if terminal_state is None:
                    raise
                logger.warning(
                    "Streaming run %s ended as %s",
                    (init_agent_state.get("course_run") or {}).get("run_id"),
                    terminal_state["execution_status"],
                )
                yield [], terminal_state
            finally:
                context.run(stream.close)
        finally:
            # Restore the caller's (or enclosing step's) budget outside every yield.
            context.run(scope.__exit__, None, None, None)

    def _log_state(self, trade_date, final_state):
        """Write a run's final state to JSON under the run's own ticker.

        FR-01 / INV-01: the log records the publication status and reason. A run the
        gate blocked carries no official rating or decision, and no candidate body or
        candidate rating — those fields are empty in the returned state already; the
        log never re-adds them.
        """
        entry = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "publication_status": final_state.get("publication_status"),
            "publication_reason": final_state.get("publication_reason"),
            "execution_status": final_state.get("execution_status"),
            "market_report": final_state.get("market_report", ""),
            "sentiment_report": final_state.get("sentiment_report", ""),
            "news_report": final_state.get("news_report", ""),
            "fundamentals_report": final_state.get("fundamentals_report", ""),
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
            },
            # A run that ended before the Trader or Research Manager (a terminal
            # budget/context refusal) never wrote these; log them empty.
            "trader_investment_plan": final_state.get("trader_investment_plan", ""),
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
            },
            "investment_plan": final_state.get("investment_plan", ""),
            "final_trade_decision": final_state.get("final_trade_decision", ""),
            "final_rating": final_state.get("final_rating") or "",
            "run_settings": self.run_settings(),
        }

        # A ticker that would escape the results directory is rejected.
        safe_ticker = safe_ticker_component(final_state["company_of_interest"])
        directory = Path(self.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            # Reports can be in any language and this file is read by a person.
            json.dump(entry, f, indent=4, ensure_ascii=False)
