"""FR-03 source adapters: receipt opt-in against the real Stage B code (r6).

Each test drives the public adapter entry point with ``_with_receipt=True`` and
normalizes the returned ``SourceText`` through the C3 owner module. Only the
network boundary is faked (``urlopen``, ``yf_retry``, ``_make_api_request``,
``_fetch_subreddit_rss``), so a single logical fetch is provable by counting
calls. Evidence refs follow the persisted ``"<source>/<vendor>:<id>"`` form.

The fixed run is AAPL as of 2026-11-10, so the request window is the baseline
seven days back: 2026-11-03..2026-11-10. Fixtures are synthetic.
"""

import copy
import datetime
import http.client
import json
from unittest.mock import MagicMock

import pytest

RUN = {
    "contract_version": "1.0",
    "run_id": "fr03-adapter-r6",
    "ticker": "AAPL",
    "as_of_date": "2026-11-10",
    "execution_status": "RUNNING",
    "request_limit": 40,
}
WINDOW_START = "2026-11-03"
WINDOW_END = "2026-11-10"
TICKER = "AAPL"


# ---------------------------------------------------------------------------
# Helpers: normalize through the public C3 boundary
# ---------------------------------------------------------------------------


def _normalize(raw, source_id, run=RUN, start=WINDOW_START, end=WINDOW_END):
    from tradingagents.agents.sentiment_coverage import normalize_source

    return normalize_source(raw, source_id, run, start, end)


def _coverage(outcomes, run=RUN):
    from tradingagents.agents.sentiment_coverage import build_sentiment_coverage

    return build_sentiment_coverage(outcomes, run)


def _finalize(coverage, assessment, run=RUN):
    from tradingagents.agents.sentiment_coverage import finalize_sentiment

    return finalize_sentiment(coverage, assessment, run)


def _assessment(score=5.0, band="Neutral", confidence="medium", narrative="n"):
    return {
        "overall_band": band,
        "overall_score": score,
        "confidence": confidence,
        "narrative": narrative,
    }


# ---------------------------------------------------------------------------
# 1. Alpha Vantage: per-article ticker_sentiment binds the article
# ---------------------------------------------------------------------------


def _av_feed():
    """A normal NEWS_SENTIMENT response: no top-level ticker_sentiment echo."""
    return {
        "items": "1",
        "feed": [{
            "title": "AAPL neutral synthetic item",
            "summary": "Synthetic balanced item",
            "source": "synthetic",
            "time_published": "20261105T120000",
            "url": "https://fixture.invalid/av",
            "ticker_sentiment": [{"ticker": "AAPL"}],
        }],
    }


def _patch_alpha_news(monkeypatch, feed):
    from tradingagents.dataflows.vendors.alpha_vantage import news as alpha_news

    calls = []

    def fake_request(function_name, params):
        calls.append((function_name, dict(params)))
        return feed

    monkeypatch.setattr(alpha_news, "_make_api_request", fake_request)
    return alpha_news, calls


@pytest.mark.unit
@pytest.mark.parametrize("as_json", [False, True], ids=["dict", "json-string"])
def test_alpha_normal_feed_counts_one_news_item(monkeypatch, as_json):
    feed = _av_feed()
    payload = json.dumps(feed) if as_json else feed
    alpha_news, calls = _patch_alpha_news(monkeypatch, payload)

    raw = alpha_news.get_news(TICKER, WINDOW_START, WINDOW_END, _with_receipt=True)
    assert len(calls) == 1
    assert calls[0][0] == "NEWS_SENTIMENT"
    assert calls[0][1]["tickers"] == "AAPL"

    outcome = _normalize(raw, "news")
    assert outcome["available"] is True
    assert outcome["valid_record_count"] == 1
    assert outcome["reason_codes"] == []
    assert "Synthetic balanced item" in str(raw)
    assert raw.source_receipt.vendor == "alpha_vantage"
    assert all(ref.startswith("news/alpha_vantage:") for ref in outcome["evidence_refs"])


@pytest.mark.unit
def test_alpha_article_about_several_tickers_still_counts(monkeypatch):
    feed = {
        "items": "1",
        "feed": [{
            "title": "AAPL and MSFT synthetic joint item",
            "summary": "Synthetic balanced item about two companies",
            "time_published": "20261105T120000",
            "url": "https://fixture.invalid/av-multi",
            "ticker_sentiment": [{"ticker": "AAPL"}, {"ticker": "MSFT"}],
        }],
    }
    alpha_news, _ = _patch_alpha_news(monkeypatch, feed)

    raw = alpha_news.get_news(TICKER, WINDOW_START, WINDOW_END, _with_receipt=True)
    outcome = _normalize(raw, "news")
    assert outcome["available"] is True
    assert outcome["valid_record_count"] == 1
    assert "Synthetic balanced item about two companies" in str(raw)


@pytest.mark.unit
def test_alpha_default_return_is_the_original_response(monkeypatch):
    feed = _av_feed()
    alpha_news, calls = _patch_alpha_news(monkeypatch, feed)

    raw = alpha_news.get_news(TICKER, WINDOW_START, WINDOW_END)
    assert raw is feed
    assert len(calls) == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "article,reason",
    [
        ({"title": "t", "summary": "s", "time_published": "20261105T120000",
          "ticker_sentiment": [{"ticker": "MSFT"}]}, "TICKER_MISMATCH"),
        ({"title": "t", "summary": "s", "ticker_sentiment": [{"ticker": "AAPL"}]},
         "UNVERIFIABLE_METADATA"),
        ({"title": "t", "summary": "s", "time_published": "20261111T000000",
          "ticker_sentiment": [{"ticker": "AAPL"}]}, "OUT_OF_WINDOW"),
    ],
    ids=["wrong-ticker", "missing-time", "out-of-window"],
)
def test_alpha_invalid_articles_do_not_count(monkeypatch, article, reason):
    feed = {"items": "1", "feed": [article]}
    alpha_news, _ = _patch_alpha_news(monkeypatch, feed)

    raw = alpha_news.get_news(TICKER, WINDOW_START, WINDOW_END, _with_receipt=True)
    outcome = _normalize(raw, "news")
    assert outcome["available"] is False
    assert outcome["valid_record_count"] == 0
    assert reason in outcome["reason_codes"]


# ---------------------------------------------------------------------------
# 2. Routed fallback still reaches the second vendor and labels it
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_routed_fallback_labels_actual_vendor(monkeypatch):
    from tradingagents.agents.analysts import sentiment_analyst as sentiment
    from tradingagents.dataflows import router
    from tradingagents.dataflows.errors import VendorUnavailableError
    from tradingagents.dataflows.vendors.alpha_vantage import news as alpha_news
    from tradingagents.graph.propagation import Propagator

    attempts = []

    def failing_yahoo(ticker, start_date, end_date, trade_date="", *, _with_receipt=False):
        attempts.append(("yfinance", _with_receipt))
        raise VendorUnavailableError("fixture: Yahoo unavailable")

    def answering_alpha(ticker, start_date, end_date, trade_date="", *, _with_receipt=False):
        attempts.append(("alpha_vantage", _with_receipt))
        monkeypatch.setattr(alpha_news, "_make_api_request", lambda *a, **k: _av_feed())
        return alpha_news.get_news(ticker, start_date, end_date, _with_receipt=_with_receipt)

    monkeypatch.setattr(
        router, "VENDOR_METHODS", {"get_news": {"yfinance": failing_yahoo,
                                                "alpha_vantage": answering_alpha}}
    )
    monkeypatch.setattr(router, "TOOLS_CATEGORIES",
                        {"news_data": {"description": "", "tools": ["get_news"]}})
    monkeypatch.setattr(router, "get_config", lambda: {"tool_vendors": {}, "data_vendors": {}})
    monkeypatch.setattr(router, "get_vendor", lambda category, method=None: "yfinance,alpha_vantage")

    raw = router.route_to_vendor(
        "get_news", TICKER, WINDOW_START, WINDOW_END, _with_receipt=True
    )
    assert len(attempts) == 2
    assert attempts[0] == ("yfinance", True)
    assert attempts[1] == ("alpha_vantage", True)
    from tradingagents.dataflows.source_receipt import SourceText

    assert isinstance(raw, SourceText)
    assert raw.source_receipt.vendor == "alpha_vantage"

    coverage = _coverage([_normalize(raw, "news")])
    assert coverage["valid_sources"] == 1
    refs = coverage["sources"]["news"]["evidence_refs"]
    assert refs and all("alpha_vantage" in ref for ref in refs)

    states = {}

    def fake_news(*args, **kwargs):
        states["with_receipt"] = kwargs.get("_with_receipt")
        return raw

    monkeypatch.setattr(sentiment.get_news, "func", fake_news, raising=False)
    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", lambda *a, **k: "")
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", lambda *a, **k: "")
    captured = {}
    llm = MagicMock()
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: captured.update(prompt=prompt)
    llm.with_structured_output.return_value = structured
    llm.invoke.return_value = MagicMock(content="NO_DATA")

    out = sentiment.create_sentiment_analyst(llm)(
        Propagator().create_initial_state(TICKER, WINDOW_END)
    )
    assert states["with_receipt"] is True
    joined = " ".join(str(m) for m in captured["prompt"])
    assert "Alpha Vantage" in joined
    assert "Yahoo Finance" not in joined
    assert out["sentiment_assessment"]["valid_sources"] == 1


# ---------------------------------------------------------------------------
# 3. StockTwits: the receipt counts exactly the rendered in-window posts
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self, *_args):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_stocktwits(monkeypatch, payload=None, error=None):
    from tradingagents.dataflows.vendors import stocktwits

    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)
        if error is not None:
            raise error
        return _FakeResponse(payload)

    monkeypatch.setattr(stocktwits, "urlopen", fake_urlopen)
    return stocktwits, calls


def _stocktwits_payload():
    return json.dumps({
        "messages": [
            {"id": 1, "created_at": "2026-11-05T12:00:00Z",
             "body": "Synthetic AAPL neutral note", "user": {"username": "u1"}},
            {"id": 2, "created_at": "2026-11-11T00:00:00Z",
             "body": "Synthetic late note", "user": {"username": "u2"}},
            {"id": 3, "created_at": "2026-11-06T00:00:00Z",
             "body": "   ", "user": {"username": "u3"}},
        ]
    }).encode()


@pytest.mark.unit
def test_stocktwits_counts_only_the_rendered_in_window_post(monkeypatch):
    stocktwits, calls = _patch_stocktwits(monkeypatch, _stocktwits_payload())

    raw = stocktwits.fetch_stocktwits_messages(
        TICKER, limit=30, start_date=WINDOW_START, end_date=WINDOW_END, _with_receipt=True
    )
    assert len(calls) == 1
    outcome = _normalize(raw, "stocktwits")
    assert outcome["available"] is True
    assert outcome["valid_record_count"] == 1
    assert "Synthetic late note" not in str(raw)
    assert "Synthetic AAPL neutral note" in str(raw)


@pytest.mark.unit
def test_stocktwits_headline_word_is_not_a_placeholder(monkeypatch):
    payload = json.dumps({"messages": [
        {"id": 1, "created_at": "2026-11-05T12:00:00Z",
         "body": "Synthetic note: data unavailable for this feed", "user": {"username": "u"}},
    ]}).encode()
    stocktwits, _ = _patch_stocktwits(monkeypatch, payload)

    raw = stocktwits.fetch_stocktwits_messages(
        TICKER, limit=30, start_date=WINDOW_START, end_date=WINDOW_END, _with_receipt=True
    )
    assert _normalize(raw, "stocktwits")["valid_record_count"] == 1


@pytest.mark.unit
def test_stocktwits_wrong_stream_response_does_not_count(monkeypatch):
    payload = json.dumps({
        "symbol": {"symbol": "MSFT"},
        "messages": [{
            "id": 1,
            "created_at": "2026-11-05T12:00:00Z",
            "body": "Synthetic MSFT note",
            "user": {"username": "u"},
        }],
    }).encode()
    stocktwits, _ = _patch_stocktwits(monkeypatch, payload)

    raw = stocktwits.fetch_stocktwits_messages(
        TICKER, limit=30, start_date=WINDOW_START, end_date=WINDOW_END, _with_receipt=True
    )
    outcome = _normalize(raw, "stocktwits")
    assert outcome["available"] is False
    assert outcome["valid_record_count"] == 0
    assert "TICKER_MISMATCH" in outcome["reason_codes"]
    assert "Synthetic MSFT note" not in str(raw)


@pytest.mark.unit
def test_stocktwits_fetch_error_and_unsupported_window(monkeypatch):
    stocktwits, _ = _patch_stocktwits(
        monkeypatch, error=http.client.BadStatusLine("fixture")
    )
    failed = stocktwits.fetch_stocktwits_messages(
        TICKER, limit=30, start_date=WINDOW_START, end_date=WINDOW_END, _with_receipt=True
    )
    assert "FETCH_ERROR" in _normalize(failed, "stocktwits")["reason_codes"]

    stocktwits, _ = _patch_stocktwits(monkeypatch, _stocktwits_payload())
    unsupported = stocktwits.fetch_stocktwits_messages(
        TICKER, limit=30, start_date=WINDOW_START, end_date=WINDOW_START, _with_receipt=True
    )
    assert "WINDOW_UNSUPPORTED" in _normalize(unsupported, "stocktwits")["reason_codes"]


# ---------------------------------------------------------------------------
# 4. Reddit: token-bound attribution, crypto base, legacy text
# ---------------------------------------------------------------------------


def _post(title, body="", created=datetime.datetime(2026, 11, 5, 12, tzinfo=datetime.UTC),
          subreddit="wallstreetbets"):
    return {
        "title": title,
        "selftext": body,
        "created_utc": None if created is None else created.timestamp(),
        "subreddit": subreddit,
    }


def _patch_reddit(monkeypatch, posts):
    from tradingagents.dataflows.vendors import reddit

    calls = []

    def fake_fetch(ticker, sub, limit, timeout, _retry=True):
        calls.append(ticker)
        return posts

    monkeypatch.setattr(reddit, "_fetch_subreddit_rss", fake_fetch)
    return reddit, calls


@pytest.mark.unit
def test_reddit_three_subreddits_count_as_one_source(monkeypatch):
    posts = [
        _post("AAPL synthetic balanced post", subreddit="wallstreetbets"),
        _post("Synthetic thread: $AAPL steady quarter", subreddit="stocks"),
        _post("AAPL neutral discussion", subreddit="investing"),
    ]
    reddit, calls = _patch_reddit(monkeypatch, posts)

    raw = reddit.fetch_reddit_posts(
        TICKER, start_date=WINDOW_START, end_date=WINDOW_END, _with_receipt=True
    )
    assert len(calls) == 1
    outcome = _normalize(raw, "reddit")
    assert outcome["available"] is True
    assert outcome["valid_record_count"] == 3
    coverage = _coverage([outcome])
    assert coverage["valid_sources"] == 1
    assert coverage["total_sources"] == 3


@pytest.mark.unit
def test_reddit_rejects_fuzzy_matches_and_keeps_valid_content(monkeypatch):
    posts = [
        _post("XAAPLY synthetic unrelated thread", "Nothing about the ticker at all"),
        _post("AAPL synthetic balanced post"),
    ]
    reddit, _ = _patch_reddit(monkeypatch, posts)

    raw = reddit.fetch_reddit_posts(
        TICKER, start_date=WINDOW_START, end_date=WINDOW_END, _with_receipt=True
    )
    outcome = _normalize(raw, "reddit")
    assert outcome["available"] is True
    assert outcome["valid_record_count"] == 1
    assert "XAAPLY" not in str(raw)
    assert "TICKER_MISMATCH" in outcome["reason_codes"]


@pytest.mark.unit
def test_reddit_crypto_pair_keeps_requested_ticker(monkeypatch):
    crypto_run = dict(RUN, ticker="BTC-USD")
    reddit, _ = _patch_reddit(monkeypatch, [_post("BTC synthetic balanced post")])

    raw = reddit.fetch_reddit_posts(
        "BTC-USD", start_date=WINDOW_START, end_date=WINDOW_END, _with_receipt=True
    )
    assert raw.source_receipt.ticker == "BTC-USD"
    outcome = _normalize(raw, "reddit", run=crypto_run)
    assert outcome["available"] is True
    assert outcome["valid_record_count"] == 1


@pytest.mark.unit
def test_reddit_default_text_is_unchanged(monkeypatch):
    reddit, _ = _patch_reddit(monkeypatch, [_post("AAPL synthetic balanced post"),
                                            _post("XAAPLY synthetic unrelated thread")])

    legacy = reddit.fetch_reddit_posts(
        TICKER, start_date=WINDOW_START, end_date=WINDOW_END
    )
    assert not hasattr(legacy, "source_receipt")
    assert "XAAPLY synthetic unrelated thread" in legacy
    assert "recent posts mentioning AAPL" in legacy


@pytest.mark.unit
def test_reddit_undated_and_blank_posts_do_not_count(monkeypatch):
    posts = [
        _post("AAPL synthetic undated post", created=None),
        _post("", "   "),
    ]
    reddit, _ = _patch_reddit(monkeypatch, posts)

    raw = reddit.fetch_reddit_posts(
        TICKER, start_date=WINDOW_START, end_date=WINDOW_END, _with_receipt=True
    )
    outcome = _normalize(raw, "reddit")
    assert outcome["available"] is False
    assert outcome["valid_record_count"] == 0


@pytest.mark.unit
def test_reddit_lowercase_request_normalizes_to_upper(monkeypatch):
    reddit, _ = _patch_reddit(monkeypatch, [_post("AAPL synthetic balanced post")])

    raw = reddit.fetch_reddit_posts(
        "aapl", start_date=WINDOW_START, end_date=WINDOW_END, _with_receipt=True
    )
    assert raw.source_receipt.ticker == "AAPL"


# ---------------------------------------------------------------------------
# 5. Core guards through the public boundary
# ---------------------------------------------------------------------------


def _source_text(source_id, text, items=(), reasons=(), ticker=TICKER,
                 vendor="fixture_vendor", start=WINDOW_START, end=WINDOW_END):
    from tradingagents.dataflows.source_receipt import SourceReceipt, SourceText

    receipt = SourceReceipt(source_id, vendor, ticker, start, end, tuple(items), tuple(reasons))
    return SourceText(text, receipt)


def _item(item_id="i1", when=datetime.datetime(2026, 11, 5, tzinfo=datetime.UTC)):
    from tradingagents.dataflows.source_receipt import ItemMeta

    return ItemMeta(item_id=item_id, published_at=when, ticker=TICKER, substantive=True)


@pytest.mark.unit
def test_headline_word_unavailable_does_not_invalidate_a_receipt():
    raw = _source_text("news", "AAPL note: data unavailable for one feed", [_item()])
    assert _normalize(raw, "news")["valid_record_count"] == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,reason",
    [
        ("", "EMPTY"),
        ("<stocktwits unavailable: TimeoutError>", "FETCH_ERROR"),
        ("<Reddit unavailable: fetch failed (r/x); this is not an absence>", "FETCH_ERROR"),
        ("<Yahoo Finance news unavailable for 2026-11-03..2026-11-10: typed>",
         "WINDOW_UNSUPPORTED"),
    ],
    ids=["empty", "stocktwits-placeholder", "reddit-placeholder", "yahoo-placeholder"],
)
def test_plain_placeholders_classify_by_anchor(raw, reason):
    outcome = _normalize(raw, "news")
    assert outcome["available"] is False
    assert reason in outcome["reason_codes"]


@pytest.mark.unit
def test_foreign_coverage_cannot_be_finalized_as_measured():
    other = dict(RUN, run_id="fr03-adapter-OTHER")
    source = _normalize(_source_text("news", "x", [_item()]), "news", run=other)
    foreign = _coverage([source], run=other)
    with pytest.raises(ValueError):
        _finalize(foreign, _assessment(5.0), run=RUN)


@pytest.mark.unit
def test_schema_rejects_boolean_score_and_accepts_measured_neutral():
    from pydantic import ValidationError

    from tradingagents.agents.schemas import SentimentBand, SentimentReport

    with pytest.raises(ValidationError):
        SentimentReport(overall_band=SentimentBand.NEUTRAL, overall_score=True,
                        confidence="low", narrative="n")
    report = SentimentReport(overall_band=SentimentBand.NEUTRAL, overall_score=5.0,
                             confidence="low", narrative="n")
    assert report.overall_score == 5.0


@pytest.mark.unit
def test_unknown_and_null_are_consistent_through_schema_and_renderer():
    from tradingagents.agents.schemas import (
        SentimentBand,
        SentimentReport,
        render_sentiment_assessment,
        render_sentiment_report,
    )

    report = SentimentReport(overall_band=SentimentBand.UNKNOWN, confidence="low", narrative="n")
    text = render_sentiment_report(report)
    assert "**UNKNOWN**" in text
    assert "Score:" not in text
    assert "**Confidence:** Low" in text

    unknown = _finalize(_coverage([_normalize(_source_text("news", "x", [_item()]), "news")]),
                        None)
    rendered = render_sentiment_assessment(unknown)
    assert rendered.startswith("**Overall Sentiment:** **UNKNOWN**")
    assert "**Confidence:** Low" in rendered


@pytest.mark.unit
def test_source_text_is_immutable_and_deepcopy_safe():
    raw = _source_text("news", "x", [_item()])
    with pytest.raises(AttributeError):
        raw.source_receipt = None
    cloned = copy.deepcopy(raw)
    assert str(cloned) == str(raw)
    assert cloned.source_receipt == raw.source_receipt


# ---------------------------------------------------------------------------
# 6. Strict fallback and coverage semantics
# ---------------------------------------------------------------------------


def _node(monkeypatch, llm, sources):
    from tradingagents.agents.analysts import sentiment_analyst as sentiment

    monkeypatch.setattr(sentiment.get_news, "func", lambda *a, **k: sources[0], raising=False)
    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", lambda *a, **k: sources[1])
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", lambda *a, **k: sources[2])
    state = {"company_of_interest": TICKER, "trade_date": WINDOW_END,
             "asset_type": "stock", "messages": []}
    return sentiment.create_sentiment_analyst(llm)(state)


def _valid_sources():
    return (_source_text("news", "AAPL headline", [_item("n1")]),
            _source_text("stocktwits", "AAPL note", [_item("s1")]),
            _source_text("reddit", "AAPL post", [_item("r1")]))


@pytest.mark.unit
@pytest.mark.parametrize("bad_score", [-1, 11, float("nan"), float("inf")],
                         ids=["neg", "over", "nan", "inf"])
def test_invalid_fallback_score_is_unknown_with_coverage_kept(monkeypatch, bad_score):
    header = f"**Overall Sentiment:** **Neutral** (Score: {bad_score}/10)\n**Confidence:** Medium"
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("no structured")
    llm.invoke.return_value = MagicMock(content=header)

    result = _node(monkeypatch, llm, _valid_sources())
    assessment = result["sentiment_assessment"]
    assert assessment["assessment_status"] == "UNKNOWN"
    assert assessment["overall_band"] == "UNKNOWN"
    assert assessment["overall_score"] is None
    assert assessment["valid_sources"] == 3
    assert "UNKNOWN" in result["sentiment_report"]


@pytest.mark.unit
def test_headerless_prose_is_unknown(monkeypatch):
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("no structured")
    llm.invoke.return_value = MagicMock(content="opaque prose with no header at all")

    assessment = _node(monkeypatch, llm, _valid_sources())["sentiment_assessment"]
    assert assessment["assessment_status"] == "UNKNOWN"
    assert assessment["valid_sources"] == 3


@pytest.mark.unit
def test_explicit_header_is_measured(monkeypatch):
    header = "**Overall Sentiment:** **Neutral** (Score: 5.0/10)\n**Confidence:** Medium\n\nok"
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("no structured")
    llm.invoke.return_value = MagicMock(content=header)

    result = _node(monkeypatch, llm, _valid_sources())
    assert result["sentiment_assessment"]["assessment_status"] == "MEASURED"
    assert "(Score: 5.0/10)" in result["sentiment_report"]


@pytest.mark.unit
@pytest.mark.parametrize("present,valid", [(0, 0), (1, 1), (2, 2), (3, 3)])
def test_coverage_counts_match_present_sources(present, valid):
    with_data = [
        _normalize(_source_text(sid, "x", [_item(f"{sid}-1")]), sid)
        for sid in ("news", "stocktwits", "reddit")[:present]
    ]
    coverage = _coverage(with_data)
    assert coverage["valid_sources"] == valid
    assert coverage["total_sources"] == 3
    measurement = _finalize(coverage, _assessment(5.0) if valid else None)
    if valid == 0:
        assert measurement["assessment_status"] == "UNKNOWN"
        assert measurement["overall_score"] is None
    else:
        assert measurement["assessment_status"] == "MEASURED"
        assert measurement["overall_score"] == 5.0
