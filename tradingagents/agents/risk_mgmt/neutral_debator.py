"""Neutral Risk Debater node with bounded, deterministic context preparation.

Requirement: NFR-02 (docs/req/requirements.yaml) -- the Neutral Risk Debater is
one of the two scoped call sites whose final model input must be bounded.
Contract: C5 "deterministic prepared context" (docs/architecture/interface-contracts.md);
the complete rendered prompt is measured and, if necessary, reduced by
:func:`tradingagents.llm_clients.context_limit.prepare_text_context` *before*
any model invocation, so preparation precedes any future C4 reservation.
ADR: ADR-001 "reduce optional history at the two scoped sites; reject irreducible
messages before budget reservation".

Context classification at this site:

* ``required_prefix`` -- role/task instructions, instrument and portfolio context,
  trader plan, current analyst reports and the conversation-history heading.
* ``optional_turns`` -- older discussion history only; removable oldest-first.
* ``required_suffix`` -- the current opponent responses, the final instructions and
  the language rule.

For a request that already fits, the prefix + every turn + suffix reproduces the
original prompt template character for character. If required content alone
exceeds the cap, ``ContextTooLarge`` propagates and ``llm.invoke`` is never called.

Integration verification item (not claimed here): C5 measures the canonical
single-user-message representation of the rendered prompt. Whether the provider
adapter normalizes a bare string argument to exactly one user/human message has
not been verified in this task and must be confirmed before any provider-wire
equivalence statement is made.
"""

import re

from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_portfolio_context_from_state,
    opponent_argument_or_opening,
    report_or_absent,
)
from tradingagents.llm_clients.context_limit import (
    TextContextParts,
    prepare_text_context,
)

# The only speaker label this module writes itself (see ``argument`` below), and
# therefore the only verified debate-turn boundary. Other debate roles are never
# assumed.
_VERIFIED_SPEAKER_PREFIX = "Neutral Analyst:"

_TURN_BOUNDARY = re.compile(r"(?<=\n)(?=" + re.escape(_VERIFIED_SPEAKER_PREFIX) + r")")


def _split_optional_history(history: str) -> tuple[str, ...]:
    """Split history into whole optional turns at verified boundaries only.

    Boundaries are taken solely at newlines followed by this module's own
    ``Neutral Analyst:`` label. Slicing neither inserts nor removes characters, so
    concatenating the returned turns reproduces ``history`` exactly. With no
    verified boundary the entire history is returned as one indivisible optional
    block, so an unverified speaker label can never cause a partial split and no
    text is ever truncated.
    """

    if not history:
        return ()

    starts = [0]
    starts.extend(match.start() for match in _TURN_BOUNDARY.finditer(history))
    if len(starts) == 1:
        # No verified boundary: keep the whole history as one optional block.
        return (history,)

    turns: list[str] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(history)
        turns.append(history[start:end])
    return tuple(turns)


def _build_prompt_prefix(
    *,
    trader_decision: str,
    instrument_context: str,
    portfolio_context: str,
    market_research_report: str,
    sentiment_report: str,
    news_report: str,
    fundamentals_report: str,
) -> str:
    """Required context up to and including the conversation-history heading.

    The template text is unchanged from the baseline prompt; the trailing space
    after the heading is where optional turns begin.
    """

    return (
        "As the Neutral Risk Analyst, your role is to provide a balanced perspective, "
        "weighing both the potential benefits and risks of the trader's decision or plan. "
        "You prioritize a well-rounded approach, evaluating the upsides and downsides while "
        "factoring in broader market trends, potential economic shifts, and diversification "
        "strategies.Here is the trader's decision:\n"
        "\n"
        f"{trader_decision}\n"
        "\n"
        "Your task is to challenge both the Aggressive and Conservative Analysts, pointing out "
        "where each perspective may be overly optimistic or overly cautious. Use insights from "
        "the following data sources to support a moderate, sustainable strategy to adjust the "
        "trader's decision:\n"
        "\n"
        f"{instrument_context}\n"
        f"{portfolio_context}\n"
        f"Market Research Report: {market_research_report}\n"
        f"Social Media Sentiment Report: {sentiment_report}\n"
        f"Latest World Affairs Report: {news_report}\n"
        f"Company Fundamentals Report: {fundamentals_report}\n"
        "Here is the current conversation history: "
    )


def _build_prompt_suffix(
    *,
    current_aggressive_response: str,
    current_conservative_response: str,
) -> str:
    """Required context after the optional turns, including the language rule.

    Starts with the separating space that follows the history in the original
    template, and ends with the language instruction exactly where the baseline
    appended it (no separator).
    """

    return (
        " Here is the last response from the aggressive analyst: "
        f"{current_aggressive_response} "
        "Here is the last response from the conservative analyst: "
        f"{current_conservative_response}. If there are no responses from the other viewpoints "
        "yet, present your own argument based on the available data.\n"
        "\n"
        "Engage actively by analyzing both sides critically, addressing weaknesses in the "
        "aggressive and conservative arguments to advocate for a more balanced approach. "
        "Challenge each of their points to illustrate why a moderate risk strategy might offer "
        "the best of both worlds, providing growth potential while safeguarding against extreme "
        "volatility. Focus on debating rather than simply presenting data, aiming to show that a "
        "balanced view can lead to the most reliable outcomes. Output conversationally as if you "
        "are speaking without any special formatting."
        f"{get_language_instruction()}"
    )


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = opponent_argument_or_opening(
            risk_debate_state.get("current_aggressive_response", ""), "aggressive analyst"
        )
        current_conservative_response = opponent_argument_or_opening(
            risk_debate_state.get("current_conservative_response", ""), "conservative analyst"
        )

        market_research_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")
        fundamentals_report = report_or_absent(state["fundamentals_report"], "fundamentals")
        instrument_context = get_instrument_context_from_state(state)
        portfolio_context = get_portfolio_context_from_state(state)

        trader_decision = state["trader_investment_plan"]

        parts = TextContextParts(
            required_prefix=_build_prompt_prefix(
                trader_decision=trader_decision,
                instrument_context=instrument_context,
                portfolio_context=portfolio_context,
                market_research_report=market_research_report,
                sentiment_report=sentiment_report,
                news_report=news_report,
                fundamentals_report=fundamentals_report,
            ),
            optional_turns=_split_optional_history(history),
            required_suffix=_build_prompt_suffix(
                current_aggressive_response=current_aggressive_response,
                current_conservative_response=current_conservative_response,
            ),
        )

        # Prepare (measure/reduce) before any model call. On irreducible required
        # content this raises ContextTooLarge and no request is made.
        prepared = prepare_text_context(parts)

        # Send exactly the single prepared user message; nothing is added after
        # preparation, so the measured representation describes this prompt.
        prepared_messages = prepared.messages
        if not prepared_messages:
            raise RuntimeError("prepared request must carry exactly one message")
        prompt = prepared_messages[0].content

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
