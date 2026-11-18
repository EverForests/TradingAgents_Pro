from typing import Any

from tradingagents.agents.state import InvestDebateState, RiskDebateState


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        asset_type: str = "stock",
        past_context: str = "",
        instrument_context: str = "",
        portfolio_context: str = "",
    ) -> dict[str, Any]:
        """Create the initial state for the agent graph.

        ``instrument_context`` is the deterministic ticker-identity string
        resolved once at run start (see
        ``TradingAgentsGraph.resolve_instrument_context``). When empty, agents
        fall back to ticker-only context via
        ``get_instrument_context_from_state``.

        The run id is minted here, at the shared run entry, so every later step
        of this run (including the analyst subgraphs, which run before the Index
        Evidence step) stamps its material with the same id. Imported lazily:
        ``setup`` imports this graph's peers and importing it at module scope
        would make the graph package circular.

        C0/C1: this is also where the one complete ``RunContext`` is created, so
        collection and the Index Evidence step *reuse* it instead of minting their
        own — a resumed run therefore keeps the identity its retained material was
        stamped with. ``execution_status`` starts ``RUNNING`` and only a normal
        finish sets ``COMPLETED``, so a run that never finished is refused as
        ``RUN_NOT_COMPLETE``.
        """
        from tradingagents.dataflows.config import get_config
        from tradingagents.graph.setup import DEFAULT_REQUEST_LIMIT, _new_run_id

        try:
            limit = get_config().get("request_limit")
        except Exception:  # noqa: BLE001 — absent config falls back to the approved default
            limit = None

        run_id = _new_run_id()
        course_run = {
            "contract_version": "1.0",
            "run_id": run_id,
            "ticker": company_name,
            "as_of_date": str(trade_date),
            "execution_status": "RUNNING",
            "request_limit": limit if limit is not None else DEFAULT_REQUEST_LIMIT,
        }

        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "asset_type": asset_type,
            "instrument_context": instrument_context,
            "trade_date": str(trade_date),
            "past_context": past_context,
            "memory_note": "",
            "portfolio_context": portfolio_context,
            # C1 v1.0 handoff: the run identity the publication gate judges the
            # candidate against. The one complete ``course_run`` is created above,
            # at the shared run entry, and reused verbatim by collection and the
            # Index Evidence step, so the analysts (which run before Index Evidence)
            # stamp their retained material with the same id the gate later checks
            # and a resumed run keeps that identity.
            "run_id": run_id,
            "execution_status": "RUNNING",
            "course_run": course_run,
            "market_evidence": [],
            "argument_index": {},
            "publication_result": None,
            # C0 ``request_limit``: the configured budget, carried on the state so
            # ``_run_context`` records it verbatim (and its own guard still
            # refuses a non-positive or non-integer setting).
            "request_limit": limit,
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "count": 0,
                }
            ),
            "risk_debate_state": RiskDebateState(
                {
                    "aggressive_history": "",
                    "conservative_history": "",
                    "neutral_history": "",
                    "history": "",
                    "latest_speaker": "",
                    "current_aggressive_response": "",
                    "current_conservative_response": "",
                    "current_neutral_response": "",
                    "count": 0,
                }
            ),
            "market_report": "",
            "fundamentals_report": "",
            "sentiment_report": "",
            "news_report": "",
            "verified_metrics": {},
            "portfolio_verified_metrics": [],
        }

    def get_graph_args(self, callbacks: list | None = None) -> dict[str, Any]:
        """Get arguments for the graph invocation.

        Args:
            callbacks: Optional list of callback handlers for tool execution tracking.
                       Note: LLM callbacks are handled separately via LLM constructor.
        """
        config = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "values",
            "config": config,
        }
