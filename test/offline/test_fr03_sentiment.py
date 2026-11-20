"""FR-03 sentiment: baseline compatibility, node wiring, prompt hygiene (r4).

``test_zero_sources_skips_model`` uses only baseline imports so it runs on the
unchanged reference (where it fails: the node calls the model with zero
sources). Everything else imports new modules inside the test.
"""

import datetime
from unittest.mock import MagicMock

import pytest

RUN = {
    "contract_version": "1.0",
    "run_id": "fr03-fixture-r1",
    "ticker": "AAPL",
    "as_of_date": "2026-11-10",
    "execution_status": "RUNNING",
    "request_limit": 40,
}
WINDOW_START = "2026-11-03"
WINDOW_END = "2026-11-10"
TICKER = "AAPL"
HEADLINE = "Synthetic headline: fixture company reports steady quarter"
STALE_TEXT = "Fabricated narrative: everything is clearly a 5/10 Neutral."


def _state():
    return {
        "company_of_interest": TICKER,
        "trade_date": WINDOW_END,
        "asset_type": "stock",
        "messages": [],
    }


def _fake_llm(captured, report=None, plain=None):
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or report
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    if plain is not None:
        llm.invoke.return_value = MagicMock(content=plain)
    return llm


def _source_text(source_id, text="fixture", items=(), reasons=()):
    from tradingagents.dataflows.source_receipt import SourceReceipt, SourceText

    receipt = SourceReceipt(
        source_id=source_id, vendor="fixture_vendor", ticker=TICKER,
        window_start=WINDOW_START, window_end=WINDOW_END,
        items=tuple(items), reason_codes=tuple(reasons),
    )
    return SourceText(text, receipt)


def _item(item_id):
    from tradingagents.dataflows.source_receipt import ItemMeta

    when = datetime.datetime(2026, 11, 5, tzinfo=datetime.UTC)
    return ItemMeta(item_id=item_id, published_at=when, ticker=TICKER, substantive=True)


def _patch_sources(monkeypatch, news, stocktwits, reddit):
    from tradingagents.agents.analysts import sentiment_analyst as sentiment

    monkeypatch.setattr(sentiment.get_news, "func", lambda *a, **k: news, raising=False)
    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", lambda *a, **k: stocktwits)
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", lambda *a, **k: reddit)


def _all_valid():
    return (
        _source_text("news", f"<start_of_news>\n{HEADLINE}\n</start_of_news>", [_item("n1")]),
        _source_text("stocktwits", "fixture st", [_item("s1")]),
        _source_text("reddit", "fixture rd", [_item("r1")]),
    )


@pytest.mark.unit
def test_prompt_neutral_requires_valid_observations():
    """The Neutral rule must describe observed balance, not silence.

    The prompt previously told the model "Neutral only when all sources are
    genuinely silent", which asks for a Neutral call on data that was never
    observed -- the exact direction the coverage boundary forbids. This reads
    the rendered instruction line directly; no model and no fetch is involved.
    """
    from tradingagents.agents.analysts.sentiment_analyst import _build_system_message

    news_block = "Synthetic AAPL news block: steady quarter, no directional claim"
    stocktwits_block = "Synthetic AAPL StockTwits block: balanced chatter, no-label"
    reddit_block = "Synthetic AAPL Reddit block: balanced discussion, no directional claim"

    prompt = _build_system_message(
        ticker=TICKER,
        start_date=WINDOW_START,
        end_date=WINDOW_END,
        news_block=news_block,
        stocktwits_block=stocktwits_block,
        reddit_block=reddit_block,
        valid_sources=3,
        news_vendor="yfinance",
    )

    band_line = prompt.split("- **overall_band**:", 1)[1].split("\n", 1)[0]

    # 1. The defect: silence is not a Neutral observation.
    assert "Neutral only when all sources are genuinely silent" not in band_line

    # 2. The required rule, stated in the same instruction line.
    assert (
        "Use Neutral when valid observations support a balanced or non-directional"
        in band_line
    )
    assert "Missing sources do not imply Neutral." in band_line
    assert "With zero valid sources, the program produces UNKNOWN with a null score" in band_line
    assert "skips the sentiment model." in band_line

    # 3. Format positive control: nothing else about the prompt changed shape.
    for band in (
        "Bullish",
        "Mildly Bullish",
        "Neutral",
        "Mixed",
        "Mildly Bearish",
        "Bearish",
    ):
        assert band in band_line
    assert "<start_of_news>" in prompt and news_block in prompt
    assert "<start_of_stocktwits>" in prompt and stocktwits_block in prompt
    assert "<start_of_reddit>" in prompt and reddit_block in prompt
    assert "## Output format for plain-text responses" in prompt
    for field in ("overall_band", "overall_score", "confidence", "narrative"):
        assert field in prompt


# ---------------------------------------------------------------------------
# BASELINE COMPATIBLE (fails on the reference: the model is called)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_zero_sources_skips_model(monkeypatch):
    """Zero-source runs must not reach the model.

    Baseline always calls the model, so the invoke counts are non-zero there
    and this fails on the count assertion -- the intended failure. A real
    SentimentReport is used so the baseline renderer runs (``.value``), keeping
    the failure a count mismatch, not an AttributeError.
    """
    from tradingagents.agents.analysts import sentiment_analyst as sentiment
    from tradingagents.agents.schemas import SentimentBand, SentimentReport

    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", lambda *a, **k: "<unavailable>")
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", lambda *a, **k: "<unavailable>")
    monkeypatch.setattr(sentiment.get_news, "func", lambda *a, **k: "<unavailable>", raising=False)

    report = SentimentReport(
        overall_band=SentimentBand.NEUTRAL, overall_score=5.0,
        confidence="low", narrative="synthetic",
    )
    captured = {}
    llm = _fake_llm(captured, report=report, plain="synthetic")
    result = sentiment.create_sentiment_analyst(llm)(_state())

    assert llm.with_structured_output.return_value.invoke.call_count == 0
    assert llm.invoke.call_count == 0
    assert "NO_DATA" in result["sentiment_report"]
    assert result["messages"][0].content == result["sentiment_report"]


# ---------------------------------------------------------------------------
# Node wiring with real receipts
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_valid_receipts_produce_measured_neutral(monkeypatch):
    from tradingagents.agents.analysts import sentiment_analyst as sentiment
    from tradingagents.agents.schemas import SentimentBand, SentimentReport

    _patch_sources(monkeypatch, *_all_valid())
    report = SentimentReport(
        overall_band=SentimentBand.NEUTRAL, overall_score=5.0,
        confidence="medium", narrative="Fixture sources are neutral.",
    )
    out = sentiment.create_sentiment_analyst(
        _fake_llm({}, report=report)
    )(_state())["sentiment_report"]
    assert "**Neutral**" in out
    assert "(Score: 5.0/10)" in out


@pytest.mark.unit
def test_zero_source_output_is_unknown_without_fabricated_score(monkeypatch):
    from tradingagents.agents.analysts import sentiment_analyst as sentiment

    _patch_sources(monkeypatch, "", "", "")
    llm = _fake_llm({}, report=None, plain=STALE_TEXT)
    out = sentiment.create_sentiment_analyst(llm)(_state())["sentiment_report"]
    assert "UNKNOWN" in out
    assert "5/10" not in out
    assert "Fabricated narrative" not in out


@pytest.mark.unit
def test_plain_strings_are_excluded_from_the_prompt(monkeypatch):
    from tradingagents.agents.analysts import sentiment_analyst as sentiment
    from tradingagents.agents.schemas import SentimentBand, SentimentReport

    _patch_sources(
        monkeypatch,
        HEADLINE,               # opaque str: no receipt
        "STTWTS-ONLY-MARKER",   # opaque str: unique content
        _source_text("reddit", "fixture rd", [_item("r1")]),
    )
    report = SentimentReport(
        overall_band=SentimentBand.NEUTRAL, overall_score=5.0,
        confidence="low", narrative="n",
    )
    captured = {}
    sentiment.create_sentiment_analyst(_fake_llm(captured, report=report))(_state())
    joined = " ".join(str(m) for m in captured["prompt"])
    assert "STTWTS-ONLY-MARKER" not in joined
    assert HEADLINE not in joined


@pytest.mark.unit
def test_explicit_header_fallback_is_accepted(monkeypatch):
    from tradingagents.agents.analysts import sentiment_analyst as sentiment

    _patch_sources(monkeypatch, *_all_valid())
    header = "**Overall Sentiment:** **Neutral** (Score: 5.0/10)\n**Confidence:** Medium\n\nok"
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
    llm.invoke.return_value = MagicMock(content=header)
    out = sentiment.create_sentiment_analyst(llm)(_state())["sentiment_report"]
    assert "**Neutral**" in out


@pytest.mark.unit
def test_both_paths_failing_redacts_to_unknown(monkeypatch):
    from tradingagents.agents.analysts import sentiment_analyst as sentiment

    _patch_sources(monkeypatch, *_all_valid())
    structured = MagicMock()
    structured.invoke.side_effect = ValueError("bad JSON")
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    llm.invoke.return_value = MagicMock(content="arbitrary opaque prose with no header")
    out = sentiment.create_sentiment_analyst(llm)(_state())["sentiment_report"]
    assert "UNKNOWN" in out
    assert "arbitrary opaque prose" not in out
