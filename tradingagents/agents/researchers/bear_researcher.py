from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
    report_or_absent,
)
from tradingagents.agents.schemas import DebateArgument
from tradingagents.agents.structured import bind_structured, invoke_structured
from tradingagents.graph.publication_gate import (
    accepted_arguments_view,
    evidence_menu,
    run_as_of_date,
    validate_argument,
)


def create_bear_researcher(llm):
    structured_llm = bind_structured(llm, DebateArgument, "Bear Researcher")

    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = opponent_argument_or_opening(
            investment_debate_state.get("current_response", ""), "bull analyst"
        )
        market_research_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")
        fundamentals_report = report_or_absent(state["fundamentals_report"], "fundamentals")
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = (
            "Company fundamentals report"
            if asset_type == "stock"
            else "Asset fundamentals report (may be unavailable for crypto)"
        )
        # FR-01: give the model this run's evidence IDs and material together, so
        # a cited ID resolves to real run material.
        evidence_block = evidence_menu(state.get("evidence_index"))

        prompt = f"""You are a Bear Analyst making the case against investing in the {target_label}. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:

- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:

{instrument_context}
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_label}: {fundamentals_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}

Available evidence (cite these exact IDs in evidence_ids; do not invent IDs):
{evidence_block}

Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the {target_label}.
""" + get_language_instruction()

        # FR-01: prefer a structured argument (captures evidence IDs in one call);
        # plain fallback carries no IDs and mints no argument.
        evidence_ids = ()
        structured = invoke_structured(structured_llm, prompt, "Bear Researcher")
        if structured is not None:
            evidence_ids = tuple(structured.evidence_ids or ())
            content = structured.argument
        else:
            content = llm.invoke(prompt).content

        argument = f"Bear Analyst: {content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        # FR-01: validate the cited evidence against this run's index with the v1
        # boundary ``validate_argument`` and, only if accepted, store the record it
        # returns. That record keeps the run's full identity, so the gate can
        # re-check ownership. ``argument_index`` is the authoritative ID -> record
        # mapping keyed by ``argument_id`` (C1 v1.0); ``accepted_arguments`` is
        # derived from it and is never a release authority.
        argument_index = dict(state.get("argument_index") or {})
        evidence_state = state.get("evidence_index")
        if evidence_state is not None and evidence_ids:
            # Imported here: ``setup`` imports this module, so a module-level
            # import of it would be circular.
            from tradingagents.graph.setup import _pending_run_context, _results_dir

            run = state.get("course_run") or _pending_run_context(state) or {}
            submission = {
                "contract_version": "1.0",
                "run_id": run.get("run_id", ""),
                # The seeded RunContext is the identity authority; fall back to the
                # state only when an older checkpoint carries no context.
                "ticker": run.get("ticker") or state.get("company_of_interest", ""),
                "as_of_date": run.get("as_of_date") or run_as_of_date(state),
                "argument_id": f"arg:bear:{run.get('run_id', '')}:"
                               f"{new_investment_debate_state['count']}",
                "speaker": "Bear Analyst",
                "claim": argument,
                "evidence_ids": list(evidence_ids),
            }
            accepted = validate_argument(
                submission, evidence_state, run, results_dir=_results_dir(),
            )
            if accepted is not None:
                argument_id = accepted["argument_id"]
                accepted = {**accepted, "claim": argument, "speaker": "Bear Analyst"}
                argument_index[argument_id] = accepted
                # As for the Bull: ``evidence_index`` is the authoritative mapping
                # the Index Evidence step built and is never rewritten here, so no
                # record loses its identity or ``content_ref``.

        return {
            "argument_index": argument_index,
            "investment_debate_state": new_investment_debate_state,
            "pending_argument": {
                "speaker": "Bear Analyst",
                "text": argument,
                "evidence_ids": list(evidence_ids),
            },
            "accepted_arguments": accepted_arguments_view(argument_index),
        }

    return bear_node
