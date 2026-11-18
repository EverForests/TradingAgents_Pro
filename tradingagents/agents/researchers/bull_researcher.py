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


def create_bull_researcher(llm):
    structured_llm = bind_structured(llm, DebateArgument, "Bull Researcher")

    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = opponent_argument_or_opening(
            investment_debate_state.get("current_response", ""), "bear analyst"
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

        prompt = f"""You are a Bull Analyst advocating for investing in the {target_label}. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
{instrument_context}
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_label}: {fundamentals_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}

Available evidence (cite these exact IDs in evidence_ids; do not invent IDs):
{evidence_block}

Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
""" + get_language_instruction()

        # FR-01: prefer a structured argument so the evidence IDs are captured in
        # the same call; fall back to plain prose only for the debate text (that
        # plain path carries no evidence IDs, so it mints no argument and cannot
        # back a published recommendation).
        evidence_ids = ()
        structured = invoke_structured(structured_llm, prompt, "Bull Researcher")
        if structured is not None:
            evidence_ids = tuple(structured.evidence_ids or ())
            content = structured.argument
        else:
            content = llm.invoke(prompt).content

        argument = f"Bull Analyst: {content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        # FR-01: validate the cited evidence against this run's index with the v1
        # boundary ``validate_argument`` and, only if it is accepted, store the
        # record it returns. That record keeps the run's full identity, so the
        # gate can re-check ownership. ``argument_index`` is the authoritative
        # ID -> record mapping keyed by ``argument_id`` (C1 v1.0);
        # ``accepted_arguments`` is derived from it for legacy readers and is
        # never a release authority.
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
                "argument_id": f"arg:bull:{run.get('run_id', '')}:"
                               f"{new_investment_debate_state['count']}",
                "speaker": "Bull Analyst",
                "claim": argument,
                "evidence_ids": list(evidence_ids),
            }
            accepted = validate_argument(
                submission, evidence_state, run, results_dir=_results_dir(),
            )
            if accepted is not None:
                argument_id = accepted["argument_id"]
                accepted = {**accepted, "claim": argument, "speaker": "Bull Analyst"}
                argument_index[argument_id] = accepted
                # ``evidence_index`` is *not* rewritten here. It is the
                # authoritative mapping the Index Evidence step built, and a
                # round-trip through ``index_to_state`` would drop each record's
                # identity and ``content_ref``, leaving the snapshot material
                # unresolvable. Accepting an argument appends to
                # ``argument_index`` only; the gate reads both mappings as stored.

        return {
            "argument_index": argument_index,
            "investment_debate_state": new_investment_debate_state,
            "pending_argument": {
                "speaker": "Bull Analyst",
                "text": argument,
                "evidence_ids": list(evidence_ids),
            },
            "accepted_arguments": accepted_arguments_view(argument_index),
        }

    return bull_node
