"""Reusable report-tree writer shared by the CLI and the programmatic API.

Writes a run's per-section markdown (analysts, research, trading, risk,
portfolio) plus a consolidated ``complete_report.md`` under ``save_path``. The
CLI and ``TradingAgentsGraph.save_reports`` both call this, so a headless / API
run produces the same on-disk report tree a CLI run does.

``complete_report.md`` also carries a ``## Verified Metrics`` section between
the header and the model-written body: one row per metric this run's registry
still vouches for, taken from the registry rather than from any list's own
numbers.
"""

from datetime import datetime
from pathlib import Path

from tradingagents.agents.rating import run_rating
from tradingagents.agents.verified_metrics import resolve_metric


def analyst_names(keys) -> list[str]:
    """The analysts as users select them: the sentiment analyst's key is "social"."""
    return ["sentiment" if key == "social" else key for key in keys or []]


def _blocked(final_state: dict) -> bool:
    """Whether this run's publication gate refused the candidate.

    The authoritative answer is the gate's ``publication_result``. Without one,
    the legacy flat field is read only to recognise a refusal; it is never used
    to *approve* anything (``save_reports`` refuses a state with no result).
    """
    from tradingagents.graph.publication_gate import publication_result_from_state

    result = publication_result_from_state(final_state)
    if result is not None:
        return not result.approved
    return final_state.get("publication_status") == "BLOCKED"


def _header(ticker: str, final_state: dict, settings: dict | None) -> str:
    """The report's title and what produced it: analysis date, version, models, analysts, vendors."""
    lines = [f"# Trading Analysis Report: {ticker}", ""]
    if final_state.get("trade_date"):
        lines.append(f"- Analysis date: {final_state['trade_date']}")
    if _blocked(final_state):
        # FR-01: a blocked run carries no official rating to print.
        lines.append(
            f"- Publication: BLOCKED ({final_state.get('publication_reason') or 'BLOCKED'})"
        )
    elif final_state.get("final_trade_decision"):
        lines.append(f"- Rating: {run_rating(final_state)}")
    lines.append(f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if settings:
        s = settings.get
        deep_provider = s("deep_think_provider") or s("llm_provider", "?")
        quick_provider = s("quick_think_provider") or s("llm_provider", "?")
        if deep_provider == quick_provider:
            models = f"{deep_provider}, deep {s('deep_think_llm', '?')}, quick {s('quick_think_llm', '?')}"
        else:   # each tier on its own provider (#1440)
            models = (f"deep {deep_provider} {s('deep_think_llm', '?')}, "
                      f"quick {quick_provider} {s('quick_think_llm', '?')}")
        lines.append(f"- TradingAgents {s('version', '?')}: {models}")
        lines.append(f"- Analysts: {', '.join(analyst_names(s('analysts')))}; "
                     f"research debate rounds {s('max_debate_rounds', '?')}, "
                     f"risk debate rounds {s('max_risk_discuss_rounds', '?')}")
        vendors = {**(s("data_vendors") or {}), **(s("tool_vendors") or {})}
        if vendors:
            lines.append("- Data vendors: " + ", ".join(f"{k} {v}" for k, v in vendors.items()))
    if final_state.get("memory_note"):
        lines.append(f"- Memory log: {final_state['memory_note']}")
    return "\n".join(lines) + "\n\n"


# The report's sections in order: (heading, folder, [(agent, file, state path)]).
_SECTIONS = (
    ("I. Analyst Team Reports", "1_analysts", (
        ("Market Analyst", "market.md", ("market_report",)),
        ("Sentiment Analyst", "sentiment.md", ("sentiment_report",)),
        ("News Analyst", "news.md", ("news_report",)),
        ("Fundamentals Analyst", "fundamentals.md", ("fundamentals_report",)),
    )),
    ("II. Research Team Decision", "2_research", (
        ("Bull Researcher", "bull.md", ("investment_debate_state", "bull_history")),
        ("Bear Researcher", "bear.md", ("investment_debate_state", "bear_history")),
        ("Research Manager", "manager.md", ("investment_plan",)),
    )),
    ("III. Trading Team Plan", "3_trading", (
        ("Trader", "trader.md", ("trader_investment_plan",)),
    )),
    ("IV. Risk Management Team Decision", "4_risk", (
        ("Aggressive Analyst", "aggressive.md", ("risk_debate_state", "aggressive_history")),
        ("Conservative Analyst", "conservative.md", ("risk_debate_state", "conservative_history")),
        ("Neutral Analyst", "neutral.md", ("risk_debate_state", "neutral_history")),
    )),
    ("V. Portfolio Manager Decision", "5_portfolio", (
        ("Portfolio Manager", "decision.md", ("final_trade_decision",)),
    )),
)


def _report_parts(final_state: dict) -> list[tuple[str, str, list[tuple[str, str, str]]]]:
    """The sections with something to say: (heading, folder, [(agent, file, text)]).

    FR-01: a BLOCKED run has no official decision, so its portfolio section is
    omitted entirely: no ``5_portfolio/decision.md`` and no decision text in the
    consolidated report. Every other section is the run's diagnostic material.
    """
    blocked = _blocked(final_state)
    parts = []
    for heading, folder, agents in _SECTIONS:
        if blocked and folder == "5_portfolio":
            continue
        written = []
        for agent, filename, path in agents:
            value = final_state
            for key in path:
                value = (value or {}).get(key)
            if value:
                written.append((agent, filename, value))
        if written:
            parts.append((heading, folder, written))
    return parts


def _verified_metrics_section(final_state: dict, ticker: str) -> str:
    """The ``## Verified Metrics`` section, or "" when nothing trustworthy is present.

    Candidates come from the Portfolio Manager's own list, but a row is written
    only for an ID this run's ``verified_metrics`` registry resolves back to, so
    a missing, altered or prior-run record is skipped. Values and units are the
    resolved record's, never the list's self-declared numbers, and an ID repeats
    at most once. The section is omitted when the list or trustworthy rows are
    absent, or when the report's ticker or analysis date disagrees with the run.
    """
    listed = final_state.get("portfolio_verified_metrics")
    run = final_state.get("course_run")
    registry = final_state.get("verified_metrics")
    if not isinstance(listed, list) or not listed:
        return ""
    if not isinstance(run, dict) or not isinstance(registry, dict) or not registry:
        return ""
    if str(run.get("ticker") or "").strip().upper() != str(ticker or "").strip().upper():
        return ""
    if str(run.get("as_of_date") or "") != str(final_state.get("trade_date") or ""):
        return ""

    rows = []
    seen = set()
    for entry in listed:
        if not isinstance(entry, dict):
            continue
        metric_id = entry.get("metric_id")
        # A usable candidate is a nonempty, non-blank string; anything else
        # (a list, a dict, a number) is skipped before de-duplication, which
        # would otherwise raise on an unhashable ID and lose the whole report.
        if not isinstance(metric_id, str) or not metric_id.strip():
            continue
        if metric_id in seen:
            continue
        record = resolve_metric(metric_id, registry, run)
        if not isinstance(record, dict) or record.get("metric_id") != metric_id:
            continue
        seen.add(metric_id)
        rows.append((metric_id, record.get("result_value"), record.get("result_unit")))
    if not rows:
        return ""

    lines = ["## Verified Metrics", "", "| metric_id | value | unit |", "| --- | --- | --- |"]
    for metric_id, value, unit in rows:
        lines.append(f"| {metric_id} | {value} | {unit} |")
    return "\n".join(lines) + "\n\n"


def write_report_tree(final_state: dict, ticker: str, save_path, settings: dict | None = None,
                      html: bool = True) -> Path:
    """Save a completed run's reports to ``save_path``; return the complete-report path.

    ``settings`` (``TradingAgentsGraph.run_settings()``) adds what produced the run
    to the report's header. ``html`` also writes ``complete_report.html``, one
    self-contained page of the same report (#1419).
    Reusing a directory replaces the generated report files, removing sections
    absent from this run and disabled HTML. Other files and directories are kept.
    """
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)
    parts = _report_parts(final_state)
    sections = []
    for heading, folder, written in parts:
        (save_path / folder).mkdir(exist_ok=True)
        for _agent, filename, text in written:
            (save_path / folder / filename).write_text(text, encoding="utf-8")
        content = "\n\n".join(f"### {agent}\n{text}" for agent, _filename, text in written)
        sections.append(f"## {heading}\n\n{content}")

    verified = _verified_metrics_section(final_state, ticker)
    (save_path / "complete_report.md").write_text(
        _header(ticker, final_state, settings) + verified + "\n\n".join(sections),
        encoding="utf-8",
    )
    if html:
        from tradingagents.report_html import render_report

        (save_path / "complete_report.html").write_text(
            render_report(ticker, final_state, settings, parts), encoding="utf-8"
        )
    else:
        (save_path / "complete_report.html").unlink(missing_ok=True)

    # Reconcile only the filenames owned by this writer; never clear the tree,
    # since callers may keep notes or other artifacts alongside the reports.
    current_files = {
        (folder, filename)
        for _heading, folder, written in parts
        for _agent, filename, _text in written
    }
    for _heading, folder, agents in _SECTIONS:
        for _agent, filename, _path in agents:
            if (folder, filename) not in current_files:
                (save_path / folder / filename).unlink(missing_ok=True)
    return save_path / "complete_report.md"
