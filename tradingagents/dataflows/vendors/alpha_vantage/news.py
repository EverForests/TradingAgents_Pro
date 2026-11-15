
import hashlib
import json
from datetime import UTC, datetime, timedelta

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.date_window import withhold_undisclosed_trades
from tradingagents.dataflows.source_receipt import ItemMeta, SourceReceipt, SourceText
from tradingagents.dataflows.vendors.alpha_vantage.common import (
    _make_api_request,
    format_datetime_for_api,
)


def _parsed_feed(raw) -> dict | None:
    """The NEWS_SENTIMENT payload as a dict, or None when it is not one.

    Error notices and rejections never reach here (``_make_api_request`` raises
    on them), but a malformed body still must not count as data.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _published_at(value) -> datetime | None:
    """Alpha Vantage ``YYYYMMDDTHHMMSS`` in UTC, or None when unparseable."""
    try:
        return datetime.strptime(str(value), "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _article_items(article: dict, ticker: str) -> tuple[ItemMeta | None, bool]:
    """One article's item metadata and whether it is about ``ticker``.

    The normal NEWS_SENTIMENT shape has no top-level ticker echo; each article
    lists its own ``ticker_sentiment`` rows. An article whose rows name this
    ticker is about it; rows naming other tickers only are not.
    """
    url = str(article.get("url") or "").strip()
    title = str(article.get("title") or "").strip()
    summary = str(article.get("summary") or "").strip()
    published = _published_at(article.get("time_published"))
    locator = url or "av:" + _digest(f"{title}|{article.get('time_published')}")
    rows = [row for row in article.get("ticker_sentiment") or () if isinstance(row, dict)]
    # An article about several companies is still about this one: any exact
    # requested-ticker row binds it. Only an article whose rows name other
    # tickers exclusively is someone else's.
    specific = any(
        str(row.get("ticker") or "").strip().upper() == ticker.strip().upper() for row in rows
    )
    item = ItemMeta(
        item_id=locator,
        published_at=published,
        ticker=ticker,
        substantive=bool(title or summary),
    )
    return item, specific


def _digest(text: str) -> str:
    """A short deterministic locator for an item with no URL of its own."""
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def _news_with_receipt(raw, ticker: str, start_date: str, end_date: str) -> SourceText:
    """Build the receipt text from the feed already fetched (no second request).

    The request itself is bound to ``ticker``; each article is attributed by its
    own ``ticker_sentiment`` rows. The prompt text lists only validated items.
    """
    def result(text: str, items: tuple[ItemMeta, ...], reasons: tuple[str, ...]) -> SourceText:
        receipt = SourceReceipt("news", "alpha_vantage", ticker, start_date, end_date, items, reasons)
        return SourceText(text, receipt)

    feed = _parsed_feed(raw)
    if feed is None:
        return result(
            "<alpha_vantage news unavailable: unreadable response>", (), ("UNVERIFIABLE_METADATA",)
        )

    start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC)
    end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=1)
    reasons: set[str] = set()
    items: list[ItemMeta] = []
    lines: list[str] = []
    for article in feed.get("feed") or ():
        if not isinstance(article, dict):
            reasons.add("UNVERIFIABLE_METADATA")
            continue
        item, specific = _article_items(article, ticker)
        if not item.substantive or item.published_at is None:
            reasons.add("UNVERIFIABLE_METADATA")
            continue
        if not specific:
            reasons.add("TICKER_MISMATCH")
            continue
        if not start <= item.published_at < end:
            reasons.add("OUT_OF_WINDOW")
            continue
        items.append(item)
        lines.append(
            f"### {article.get('title', '')} (source: {article.get('source') or 'Alpha Vantage'})\n"
            + (f"{article.get('summary')}\n" if article.get("summary") else "")
            + (f"Link: {article.get('url')}\n" if article.get("url") else "")
        )

    if not items:
        reason = ("OUT_OF_WINDOW" if "OUT_OF_WINDOW" in reasons
                  else "TICKER_MISMATCH" if "TICKER_MISMATCH" in reasons
                  else "UNVERIFIABLE_METADATA" if reasons else "EMPTY")
        return result(
            f"<no Alpha Vantage news for {ticker} between {start_date} and {end_date}>",
            (), (reason,),
        )

    header = f"## {ticker} News (Alpha Vantage), from {start_date} to {end_date}:\n\n"
    return result(header + "\n".join(lines), tuple(items), tuple(sorted(reasons)))


def get_news(ticker, start_date, end_date, *, _with_receipt: bool = False) -> dict[str, str] | str:
    """Returns live and historical market news & sentiment data from premier news outlets worldwide.

    Covers stocks, cryptocurrencies, forex, and topics like fiscal policy, mergers & acquisitions, IPOs.

    Args:
        ticker: Stock symbol for news articles.
        start_date: Start date for news search.
        end_date: End date for news search.

    Returns:
        Dictionary containing news sentiment data or JSON string. With
        ``_with_receipt=True``, a ``SourceText`` for the validated items only.
    """

    # Without a limit the endpoint returns 50 articles, each with per-ticker
    # sentiment arrays, and all of it reaches the prompt.
    params = {
        "tickers": ticker,
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(end_date, end_of_day=True),
        "limit": str(get_config()["news_article_limit"]),
    }

    raw = _make_api_request("NEWS_SENTIMENT", params)
    if not _with_receipt:
        return raw
    return _news_with_receipt(raw, ticker, start_date, end_date)


def get_global_news(as_of_date, look_back_days: int | None = None, limit: int | None = None) -> dict[str, str] | str:
    """Returns global market news & sentiment data without ticker-specific filtering.

    Covers broad market topics like financial markets, economy, and more.

    Args:
        as_of_date: Current date in yyyy-mm-dd format.
        look_back_days: Number of days to look back; ``None`` uses
            ``global_news_lookback_days`` from the active config.
        limit: Maximum number of articles; ``None`` uses
            ``global_news_article_limit`` from the active config.

    Returns:
        Dictionary containing global news sentiment data or JSON string.
    """
    from datetime import datetime, timedelta

    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]

    curr_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    params = {
        "topics": "financial_markets,economy_macro,economy_monetary",
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(as_of_date, end_of_day=True),
        "limit": str(limit),
    }

    return _make_api_request("NEWS_SENTIMENT", params)


def get_insider_transactions(symbol: str, as_of_date: str | None = None) -> dict[str, str] | str:
    """Returns latest and historical insider transactions by key stakeholders.

    Covers transactions by founders, executives, board members, etc.

    Args:
        symbol: Ticker symbol. Example: "IBM".
        as_of_date: The analysis date (yyyy-mm-dd); a past one withholds them.

    Returns:
        Dictionary containing insider transaction data or JSON string.
    """

    withheld = withhold_undisclosed_trades(as_of_date, symbol)
    if withheld:
        return withheld
    return _make_api_request("INSIDER_TRANSACTIONS", {"symbol": symbol})
