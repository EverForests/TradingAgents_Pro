from typing import Annotated, Any
from uuid import uuid4

from langgraph.graph import MessagesState
from typing_extensions import TypedDict

CONTRACT_VERSION = "1.0"
# Product profile for one single-stock run (see the interface contracts).
REQUEST_LIMIT = 40


def new_course_run(ticker: str, as_of_date: str) -> dict[str, Any]:
    """A fresh C0 run identity: new ``run_id``, RUNNING, product request limit.

    Lives here, beside the state it fills, so agents can mint an identity for a
    direct entry without importing the graph package (which imports the agents).
    """
    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": f"run-{uuid4().hex}",
        "ticker": ticker,
        "as_of_date": as_of_date,
        "execution_status": "RUNNING",
        "request_limit": REQUEST_LIMIT,
    }


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
    past_context: Annotated[str, "Memory log context for the Portfolio Manager (same-ticker decisions + cross-ticker lessons), written by the Memory Log step"]
    memory_note: Annotated[str, "What the Memory Log step could not settle or read this run, for the report; empty when all went well"]
    portfolio_context: Annotated[str, "Caller-supplied holdings and cash, rendered at run start; empty when not provided"]

    # Run identity (C0) and the authoritative sentiment record (C3). Both are
    # separate keys: a node writes only the key it owns, and no parallel node
    # overwrites a whole shared dictionary.
    course_run: Annotated[dict, "Run identity and execution state: run_id, ticker, as_of_date"]
    sentiment_assessment: Annotated[
        dict | None, "Authoritative sentiment record: coverage, band, score, confidence, narrative"
    ]
