"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call. FR-01 / INV-01: the manager
writes **only** the internal candidate (``candidate_decision``,
``candidate_rating``, ``candidate_argument_ids``); the publication gate promotes
it to the official ``final_trade_decision`` / ``final_rating`` on approval, so a
refused candidate never reaches the memory log, CLI display or saved reports.
When a provider does not expose structured output, the agent falls back to
free-text generation and the rating is read from that text — but with no
argument ids, so the gate blocks it.

Both decision paths meet before the node returns. There the run's verified
metrics are re-read by ID with ``resolve_metric`` and passed on as
``portfolio_verified_metrics``; the model's text is never a source of numbers
and no extra request is made.
"""

from __future__ import annotations

from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_portfolio_context_from_state,
)
from tradingagents.agents.rating import parse_rating
from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.structured import NO_EXTERNAL_TOOLS, bind_structured, invoke_structured
from tradingagents.agents.verified_metrics import resolve_metric


def _resolved_metrics(state) -> list:
    """This run's verified metrics, re-read by ID, as {metric_id, result_value, result_unit}.

    A missing, null or wrong-typed course_run or registry yields an empty list,
    as does a registry whose records resolve to nothing (empty table, a prior
    run's IDs, or an unknown ID). Order follows the registry's own key order
    and is the same on both decision paths. The passed state is only read.
    """
    run = state.get("course_run") if isinstance(state, dict) else None
    registry = state.get("verified_metrics") if isinstance(state, dict) else None
    if not isinstance(run, dict) or not isinstance(registry, dict) or not registry:
        return []
    resolved = []
    for metric_id in registry:
        record = resolve_metric(metric_id, registry, run)
        if not isinstance(record, dict):
            continue
        if record.get("metric_id") != metric_id:
            continue
        resolved.append({
            "metric_id": metric_id,
            "result_value": record.get("result_value"),
            "result_unit": record.get("result_unit"),
        })
    return resolved


def create_portfolio_manager(llm):
    # Local import preserves the graph/agents package initialization boundary.
    from tradingagents.graph.publication_gate import _resolve_selections, _select_aliases

    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        portfolio_context = get_portfolio_context_from_state(state)

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

        # FR-01: the decision must rest on arguments the program accepted. The
        # accepted argument IDs are injected here so the manager can cite them.
        # FR-01 reference adapter: each listed line also offers a short local
        # selection ('= A1'), built from this same list and frozen for this
        # invocation, so the model need not copy a long run-bound ID.
        accepted = state.get("accepted_arguments") or []
        accepted_line = ""
        argument_aliases: dict[str, str] = {}
        if accepted:
            argument_aliases = _select_aliases(
                [a["argument_id"] for a in accepted], "A",
            )
            selections = {
                reference: alias for alias, reference in argument_aliases.items()
            }
            listed = "\n".join(
                f"- {a['argument_id']} ({a['speaker']}; evidence {', '.join(a['evidence_ids'])})"
                + (f" = {selections[a['argument_id']]}"
                   if a["argument_id"] in selections else "")
                for a in accepted
            )
            accepted_line = (
                f"\n**Accepted arguments** (cite their short selections, such as 'A1', "
                f"in argument_ids; an exact full ID is also accepted):\n{listed}\n"
            )

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

{portfolio_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
**Risk Analysts Debate History:**
{history}
{accepted_line}

---

Ground every conclusion in specific evidence from the analysts. The risk debate always contains conflicting stances; deciding which is stronger is the job, so conflict alone is not a reason to Hold. Commit to the stronger case, sized by how decisively it wins. Choose Hold only when the evidence is still balanced after that weighing, or too thin to support a call; do not force a direction to appear decisive. Weigh the analysts on their merits, independent of speaking order.

## Output

Write these sections, in this order, starting with the rating on its own line:

- **Rating**: exactly one of Buy / Overweight / Hold / Underweight / Sell
- **Executive Summary**: the call and how to act on it
- **Investment Thesis**: the evidence that decided it, and what would change it

{NO_EXTERNAL_TOOLS}{get_language_instruction()}"""

        # The typed rating is the decision; the rendered text only carries it.
        # Read back from text, a rating the thesis quotes could replace it.
        decision = invoke_structured(structured_llm, prompt, "Portfolio Manager")
        if decision is not None:
            candidate_body = render_pm_decision(decision)
            candidate_rating = decision.rating.value
            # FR-01 reference adapter: an A-selection becomes the canonical
            # accepted-argument ID the gate rechecks. An unknown or shortened
            # selection is kept as written, so the gate refuses the candidate
            # instead of dropping the reference.
            argument_ids = _resolve_selections(
                decision.argument_ids or [], argument_aliases, "Portfolio Manager",
            )
        else:
            # FR-01: no free-text rating fallback around the gate. A free-text
            # answer carries no structured argument_ids, so the candidate decision
            # is kept but cannot publish — the gate blocks it for lack of evidence.
            candidate_body = llm.invoke(prompt).content
            candidate_rating = parse_rating(candidate_body)
            argument_ids = []

        # Both paths meet here: re-read this run's verified metrics by ID.
        portfolio_verified_metrics = _resolved_metrics(state)

        new_risk_debate_state = {
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        # FR-01 / INV-01: the Portfolio Manager writes only the internal candidate.
        # The publication gate promotes it to the official fields on approval; on
        # refusal nothing here can reach an official sink.
        return {
            "risk_debate_state": new_risk_debate_state,
            "candidate_decision": candidate_body,
            "candidate_rating": candidate_rating,
            "candidate_argument_ids": argument_ids,
            "portfolio_verified_metrics": portfolio_verified_metrics,
        }

    return portfolio_manager_node
