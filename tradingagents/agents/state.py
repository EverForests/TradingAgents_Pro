from typing import Annotated

from langgraph.graph import MessagesState
from typing_extensions import TypedDict


# Researcher team state
class InvestDebateState(TypedDict):
    bull_history: Annotated[
        str, "Bullish Conversation history"
    ]
    bear_history: Annotated[
        str, "Bearish Conversation history"
    ]
    history: Annotated[str, "Conversation history"]
    current_response: Annotated[str, "Latest response"]
    count: Annotated[int, "Length of the current conversation"]


# Risk management team state
class RiskDebateState(TypedDict):
    aggressive_history: Annotated[
        str, "Aggressive Agent's Conversation history"
    ]
    conservative_history: Annotated[
        str, "Conservative Agent's Conversation history"
    ]
    neutral_history: Annotated[
        str, "Neutral Agent's Conversation history"
    ]
    history: Annotated[str, "Conversation history"]
    latest_speaker: Annotated[str, "Analyst that spoke last"]
    current_aggressive_response: Annotated[
        str, "Latest response by the aggressive analyst"
    ]
    current_conservative_response: Annotated[
        str, "Latest response by the conservative analyst"
    ]
    current_neutral_response: Annotated[
        str, "Latest response by the neutral analyst"
    ]
    count: Annotated[int, "Length of the current conversation"]


class AgentState(MessagesState):
    company_of_interest: Annotated[str, "Company that we are interested in trading"]
    asset_type: Annotated[str, "Asset type under analysis such as stock or crypto"]
    instrument_context: Annotated[str, "Deterministic ticker identity resolved at run start"]
    trade_date: Annotated[str, "The analysis date; data is served as of it"]

    # research step
    market_report: Annotated[str, "Report from the Market Analyst"]
    sentiment_report: Annotated[str, "Report from the Sentiment Analyst"]
    news_report: Annotated[str, "Report from the News Analyst on company and world news"]
    fundamentals_report: Annotated[str, "Report from the Fundamentals Analyst"]

    # researcher team discussion step
    investment_debate_state: Annotated[
        InvestDebateState, "Current state of the debate on if to invest or not"
    ]
    investment_plan: Annotated[str, "Investment plan from the Research Manager"]

    trader_investment_plan: Annotated[str, "Transaction proposal from the Trader"]

    # risk management team discussion step
    risk_debate_state: Annotated[
        RiskDebateState, "Current state of the debate on evaluating risk"
    ]
    final_trade_decision: Annotated[str, "Final decision from the Portfolio Manager"]
    final_rating: Annotated[str, "The Portfolio Manager's 5-tier rating, or REVIEW when it has none"]
    # FR-01 / INV-01: the publication gate's single release result, written by
    # publication_gate.apply() before any sink reads the run.
    publication_status: Annotated[str, "APPROVED or BLOCKED, set by the publication gate"]
    publication_reason: Annotated[str, "INVALID_RATING or INSUFFICIENT_EVIDENCE when BLOCKED, else empty"]
    publication_chain: Annotated[list, "Resolved (argument_id, evidence_id, source) links when APPROVED"]
    # C1 v1.0: the run identity the gate judges against, the authoritative
    # ID -> record mappings, and the one publication result every sink reads.
    course_run: Annotated[dict, "RunContext for this run (contract_version, run_id, ticker, as_of_date, execution_status, request_limit)"]
    execution_status: Annotated[str, "C0 execution state: COMPLETED, or a terminal failure such as BUDGET_EXHAUSTED"]
    request_limit: Annotated[int, "C0 per-run request budget, a positive integer (approved default 40)"]
    argument_index: Annotated[dict, "Accepted arguments keyed by argument_id (FR-01, C1 v1.0)"]
    publication_result: Annotated[dict, "The gate's authoritative PublicationResult, set once per run"]
    evidence_index: Annotated[dict, "Run-scoped evidence as an evidence_id -> record mapping, built by Index Evidence from retained material (FR-01)"]
    market_evidence: Annotated[list, "Verified snapshot receipts this run's market analyst retained, handed up from its own subgraph (R8-B §4)"]
    candidate_decision: Annotated[str, "Internal candidate body, never read by an official sink"]
    candidate_rating: Annotated[str, "Internal candidate 5-tier rating, only promoted to final_rating by the gate"]
    pending_argument: Annotated[dict, "The most recent Bull/Bear argument awaiting evidence validation (FR-01)"]
    accepted_arguments: Annotated[list, "Accepted (argument_id, speaker, evidence_ids) records for the Portfolio Manager (FR-01)"]
    candidate_argument_ids: Annotated[list, "Argument IDs the Portfolio Manager cited for its candidate (FR-01)"]
    run_id: Annotated[str, "This run's stable identifier, minted once and reused on resume (FR-01)"]
    past_context: Annotated[str, "Memory log context for the Portfolio Manager (same-ticker decisions + cross-ticker lessons), written by the Memory Log step"]
    memory_note: Annotated[str, "What the Memory Log step could not settle or read this run, for the report; empty when all went well"]
    portfolio_context: Annotated[str, "Caller-supplied holdings and cash, rendered at run start; empty when not provided"]
