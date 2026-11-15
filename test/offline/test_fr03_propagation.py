"""FR-03 propagation: run identity, reporting, consumers, adapters (r4).

Run identity lives under ``course_run`` on the initial state. The offline
LangGraph test uses the *real* sentiment node (zero sources patched) alongside
fake market/fundamental nodes and an explicit state schema that merges channel
writes, so "other analyses continue" is proven through graph execution.
"""

from unittest.mock import MagicMock

import pytest

TICKER = "AAPL"
TRADE_DATE = "2026-11-10"
HEADLINE = "Synthetic headline: fixture company reports steady quarter"


# ---------------------------------------------------------------------------
# Run identity
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_propagator_issues_fresh_course_run_identity():
    from tradingagents.graph.propagation import Propagator

    prop = Propagator()
    first = prop.create_initial_state(TICKER, TRADE_DATE)
    second = prop.create_initial_state(TICKER, TRADE_DATE)

    for state in (first, second):
        for field in ("run_id", "ticker", "as_of_date"):
            assert state["course_run"][field]
        assert "sentiment_assessment" in state

    assert first["course_run"]["run_id"] != second["course_run"]["run_id"]
    assert first.get("sentiment_assessment") is None


@pytest.mark.unit
def test_legacy_node_entry_without_run_still_yields_identity(monkeypatch):
    from tradingagents.agents.analysts import sentiment_analyst as sentiment

    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", lambda *a, **k: "")
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", lambda *a, **k: "")
    monkeypatch.setattr(sentiment.get_news, "func", lambda *a, **k: "", raising=False)

    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("no structured")
    llm.invoke.return_value = MagicMock(content="NO_DATA")
    state = {"company_of_interest": TICKER, "trade_date": TRADE_DATE, "messages": []}
    result = sentiment.create_sentiment_analyst(llm)(state)
    assert result["sentiment_assessment"]["run_id"]


# ---------------------------------------------------------------------------
# Reporting: coverage text reaches markdown and HTML
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unknown_sentiment_written_to_markdown_and_html(tmp_path):
    from tradingagents.reporting import write_report_tree

    text = "**Overall Sentiment:** **UNKNOWN**\n\nNO_DATA: all sources empty"
    write_report_tree(
        {"trade_date": TRADE_DATE, "sentiment_report": text},
        TICKER, tmp_path, settings=None, html=True,
    )
    assert "NO_DATA: all sources empty" in (tmp_path / "complete_report.md").read_text("utf-8")
    assert "NO_DATA" in (tmp_path / "complete_report.html").read_text("utf-8")


# ---------------------------------------------------------------------------
# Downstream consumers read the actual node's output (measured and UNKNOWN)
# ---------------------------------------------------------------------------


def _run_sentiment(monkeypatch, news, stocktwits, reddit, report, plain):
    from tradingagents.agents.analysts import sentiment_analyst as sentiment
    from tradingagents.graph.propagation import Propagator

    monkeypatch.setattr(sentiment.get_news, "func", lambda *a, **k: news, raising=False)
    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", lambda *a, **k: stocktwits)
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", lambda *a, **k: reddit)

    structured = MagicMock()
    structured.invoke.return_value = report
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    llm.invoke.return_value = MagicMock(content=plain)

    state = Propagator().create_initial_state(TICKER, TRADE_DATE)
    state.update(sentiment.create_sentiment_analyst(llm)(state))
    return state


@pytest.mark.unit
@pytest.mark.parametrize("zero_sources", [False, True], ids=["measured", "no_data"])
def test_five_consumers_see_actual_sentiment_text(monkeypatch, zero_sources):
    from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
    from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
    from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
    from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
    from tradingagents.agents.schemas import SentimentBand, SentimentReport

    if zero_sources:
        state = _run_sentiment(monkeypatch, "", "", "", None, "opaque prose")
    else:
        import datetime

        from tradingagents.dataflows.source_receipt import ItemMeta, SourceReceipt, SourceText

        published = datetime.datetime(2026, 11, 5, tzinfo=datetime.UTC)

        def _txt(sid):
            meta = ItemMeta(item_id=f"{sid}-1", published_at=published,
                            ticker=TICKER, substantive=True)
            return SourceText(
                "fixture",
                SourceReceipt(sid, "fixture_vendor", TICKER, "2026-11-03", TRADE_DATE,
                              items=(meta,), reason_codes=()),
            )
        report = SentimentReport(
            overall_band=SentimentBand.NEUTRAL, overall_score=5.0,
            confidence="medium", narrative="n",
        )
        state = _run_sentiment(monkeypatch, _txt("news"), _txt("stocktwits"), _txt("reddit"), report, "n")

    sentiment_text = state["sentiment_report"]
    expected = "UNKNOWN" if zero_sources else "**Neutral** (Score: 5.0/10)"
    assert expected in sentiment_text

    captured = []
    llm = MagicMock()
    llm.invoke.side_effect = lambda prompt: captured.append(str(prompt)) or MagicMock(content="")

    state["investment_debate_state"] = {"history": "", "current_response": "", "count": 0}
    state["risk_debate_state"] = {"history": "", "count": 0}
    state["trader_investment_plan"] = "Hold"
    for factory in (create_bull_researcher, create_bear_researcher, create_aggressive_debator,
                    create_conservative_debator, create_neutral_debator):
        factory(llm)(state)

    assert len(captured) == 5
    for prompt in captured:
        assert expected in prompt


# ---------------------------------------------------------------------------
# Real graph: other analysts continue after a zero-source sentiment run
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_other_analyses_continue_after_zero_source_sentiment(monkeypatch):
    from langgraph.graph import END, StateGraph
    from typing_extensions import TypedDict

    from tradingagents.agents.analysts import sentiment_analyst as sentiment

    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", lambda *a, **k: "")
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", lambda *a, **k: "")
    monkeypatch.setattr(sentiment.get_news, "func", lambda *a, **k: "", raising=False)

    fake_llm = MagicMock()
    fake_llm.with_structured_output.side_effect = NotImplementedError("zero sources")
    fake_llm.invoke.return_value = MagicMock(content="should not be used")

    class S(TypedDict, total=False):
        company_of_interest: str
        trade_date: str
        asset_type: str
        messages: list
        market_report: str
        sentiment_report: str
        fundamentals_report: str

    graph = StateGraph(S)
    graph.add_node("market", lambda s: {"market_report": "market ran"})
    graph.add_node("sentiment", sentiment.create_sentiment_analyst(fake_llm))
    graph.add_node("fundamentals", lambda s: {"fundamentals_report": "fundamentals ran"})
    graph.set_entry_point("market")
    graph.add_edge("market", "sentiment")
    graph.add_edge("sentiment", "fundamentals")
    graph.add_edge("fundamentals", END)

    state = {"company_of_interest": TICKER, "trade_date": TRADE_DATE,
             "asset_type": "stock", "messages": []}
    final = graph.compile().invoke(state)

    assert "NO_DATA" in final["sentiment_report"]
    assert "UNKNOWN" in final["sentiment_report"]
    assert fake_llm.with_structured_output.return_value.invoke.call_count == 0
    assert fake_llm.invoke.call_count == 0
    assert final["market_report"] == "market ran"
    assert final["fundamentals_report"] == "fundamentals ran"


# ---------------------------------------------------------------------------
# Adapter boundary: one network fetch, actual receipt
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_yfinance_news_receipt_with_single_fetch(monkeypatch):
    from tradingagents.dataflows.source_receipt import SourceText
    from tradingagents.dataflows.vendors.yahoo import news as yahoo_news

    calls = {"n": 0}
    article = {
        "content": {
            "title": HEADLINE, "summary": "",
            "provider": {"displayName": "fixture"},
            "canonicalUrl": {"url": "https://example.invalid/a"},
            "pubDate": "2026-11-05T12:00:00Z",
        }
    }

    def fake_retry(thunk):          # the adapter's only network seam
        calls["n"] += 1
        return [article] if calls["n"] == 1 else []

    monkeypatch.setattr(yahoo_news, "yf_retry", fake_retry)
    result = yahoo_news.get_news_yfinance(TICKER, "2026-11-03", TRADE_DATE, _with_receipt=True)

    assert isinstance(result, SourceText)
    receipt = result.source_receipt
    assert receipt.vendor == "yfinance"
    assert receipt.ticker == TICKER
    assert receipt.items and receipt.items[0].published_at is not None
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# CLI statuses from the real MessageBuffer
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cli_marks_sentiment_completed_once_report_lands():
    from cli.display import MessageBuffer, update_analyst_statuses

    buffer = MessageBuffer()
    buffer.init_for_analysis(["market", "social"])
    update_analyst_statuses(buffer, {"sentiment_report": "**Overall Sentiment:** **UNKNOWN**"})
    assert buffer.agent_status["Sentiment Analyst"] == "completed"
    assert buffer.agent_status["Market Analyst"] == "in_progress"
