"""StockTwits public symbol-stream fetcher.

StockTwits exposes a per-symbol message stream at
``api.stocktwits.com/api/2/streams/symbol/{ticker}.json`` that requires no
API key, no OAuth, and no registration. Each message includes a
user-labeled sentiment field (``Bullish``/``Bearish``/null), the message
body, timestamp, and posting user.

The function is deliberately self-contained: short timeout, graceful
degradation on any HTTP or parse failure, and a string return type so
the calling agent gets a uniform interface regardless of whether the
network call succeeded.
"""

from __future__ import annotations

import contextlib
import hashlib
import html
import http.client
import json
import logging
from datetime import datetime
from urllib.request import Request, urlopen

from tradingagents.dataflows.date_window import coverage_gap, in_window
from tradingagents.dataflows.source_receipt import ItemMeta, SourceReceipt, SourceText
from tradingagents.dataflows.symbols import crypto_base

logger = logging.getLogger(__name__)

_API = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"


def _created_at(message) -> datetime | None:
    """Parse a message's ISO 8601 ``created_at``; None when missing or malformed."""
    raw = message.get("created_at")
    if not raw:
        return None
    with contextlib.suppress(ValueError, TypeError):
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return None


def _within_window(messages, start_date, end_date):
    """Keep only messages published in [start_date, end_date] (look-ahead safe).

    No window (both None) leaves the list untouched for live callers. A message
    whose ``created_at`` (ISO 8601) is unparseable is dropped in a historical
    window, since we can't prove it isn't from after the as-of date (#1220).
    """
    if not (start_date and end_date):
        return messages
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    return [m for m in messages if in_window(_created_at(m), start_dt, end_dt)]


def _body(message) -> str:
    """The message text; the API serves it HTML-escaped (``&amp;``, ``&#39;``)."""
    return html.unescape(message.get("body") or "")


def _stocktwits_symbol(ticker: str) -> str:
    """Map a crypto pair to StockTwits' ``<BASE>.X`` convention.

    StockTwits lists crypto as ``BTC.X`` (Yahoo's ``BTC-USD`` form 404s), so any
    crypto symbol resolves to its base plus ``.X``; other symbols pass through
    upper-cased.
    """
    base = crypto_base(ticker)
    return f"{base}.X" if base else ticker.strip().upper()


def _same_symbol(echoed: str, ticker: str) -> bool:
    """Whether a response's echoed symbol names the requested stream.

    Crypto streams answer as ``<BASE>.X``, so an echo of that form matches the
    pair it was requested for; every other comparison is exact and caseless.
    """
    left = echoed.strip().upper()
    if not left:
        return False
    wanted = _stocktwits_symbol(ticker)
    base = crypto_base(ticker)
    accepted = {wanted}
    if base:
        accepted.add(f"{base}.X")
        accepted.add(base.upper())
    else:
        accepted.add(ticker.strip().upper())
    return left in accepted


def _displayed_messages(messages, limit: int) -> list:
    """The messages whose bodies the rendered block actually shows (newest first)."""
    return messages[:limit]


def _message_meta(message, ticker: str) -> ItemMeta:
    """Metadata for one rendered message: created time, cashtag, id, no body."""
    message_id = message.get("id")
    user = (message.get("user") or {}).get("username")
    locator = f"st:{message_id}" if message_id is not None else (
        "st:" + hashlib.sha1(f"{message.get('created_at')}|{user}".encode()).hexdigest()[:16]
    )
    return ItemMeta(
        item_id=locator,
        published_at=_created_at(message),
        ticker=ticker,
        substantive=bool(_body(message).strip()),
    )


def fetch_stocktwits_messages(
    ticker: str,
    limit: int = 30,
    timeout: float = 10.0,
    start_date: str | None = None,
    end_date: str | None = None,
    screen=None,
    *,
    _with_receipt: bool = False,
) -> str:
    """Fetch recent StockTwits messages for ``ticker`` and return them as a
    formatted plaintext block ready for prompt injection.

    When ``start_date``/``end_date`` (yyyy-mm-dd) are given, messages are trimmed
    to that window, so a historical run never sees today's chatter (#1220). The
    public stream only serves recent messages, so a window it cannot reach is
    reported as unavailable rather than as silence.

    ``screen``, when given, takes the message bodies and returns a keep flag per
    message and a note line that heads the block.

    Returns a placeholder string when the endpoint is unreachable, the
    symbol has no messages, or the response shape is unexpected — the
    caller never has to special-case None or exceptions.

    ``_with_receipt=True`` returns the same text as a ``SourceText`` carrying a
    receipt for exactly the posts its block shows. The default is unchanged.
    """
    def result(text: str, items: tuple = (), reasons: tuple[str, ...] = ()) -> str:
        if not _with_receipt:
            return text
        receipt = SourceReceipt(
            source_id="stocktwits",
            vendor="stocktwits",
            ticker=ticker,
            window_start=start_date or "",
            window_end=end_date or "",
            items=items,
            reason_codes=reasons,
        )
        return SourceText(text, receipt)

    if (start_date and not end_date) or (end_date and not start_date):
        return result(
            f"<StockTwits window unsupported for ${ticker.upper()}: both dates are required>",
            reasons=("WINDOW_UNSUPPORTED",),
        )

    url = _API.format(ticker=_stocktwits_symbol(ticker))
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        # OSError covers URLError/TimeoutError/connection resets; HTTPException
        # covers chunked-transfer errors (IncompleteRead/BadStatusLine, #1024).
        logger.warning("StockTwits fetch failed for %s: %s", ticker, exc)
        return result(
            f"<stocktwits unavailable: {type(exc).__name__}>", reasons=("FETCH_ERROR",)
        )

    fetched = data.get("messages", []) if isinstance(data, dict) else []
    if _with_receipt and isinstance(data, dict):
        # The endpoint binds to the requested symbol; a payload that names a
        # different symbol belongs to another stream, so nothing in it is
        # evidence about this ticker. A payload that echoes nothing at all is
        # left to the request binding above.
        echoed = data.get("symbol")
        echoed = echoed.get("symbol") if isinstance(echoed, dict) else echoed
        if isinstance(echoed, str) and echoed.strip() and not _same_symbol(echoed, ticker):
            return result(
                f"<no StockTwits messages for ${ticker.upper()}: response is for "
                f"{echoed.strip().upper()}, not the requested stream>",
                reasons=("TICKER_MISMATCH",),
            )
    messages = _within_window(fetched, start_date, end_date)
    if not messages:
        if start_date and end_date:
            gap = coverage_gap(
                (_created_at(m) for m in fetched), start_date, end_date,
                "StockTwits", f"messages about ${ticker.upper()}",
            )
            # A window the feed cannot reach is unsupported, not empty.
            reason = "OUT_OF_WINDOW" if fetched else "EMPTY"
            if _with_receipt and gap:
                reason = "WINDOW_UNSUPPORTED"
            return result(
                gap or (
                    f"<no StockTwits messages for ${ticker.upper()} within "
                    f"{start_date}..{end_date}>"
                ),
                reasons=(reason,),
            )
        return result(
            f"<no StockTwits messages found for ${ticker.upper()}>",
            reasons=("EMPTY",),
        )

    note = ""
    if screen:
        keep, note = screen([_body(m) for m in messages])
        screened = len(messages)
        messages = [m for m, kept in zip(messages, keep, strict=True) if kept]
        if not messages:
            return result(
                f"{note}\n\n<none of the {screened} StockTwits messages is about ${ticker.upper()}>",
                reasons=("EMPTY",),
            )

    if _with_receipt:
        # The receipt must describe exactly the rendered content: a blank body
        # is not admissible evidence, so it is left out of the block and the
        # ratio too. Legacy callers keep the existing block.
        messages = [m for m in messages if _body(m).strip()]
        if not messages:
            return result(
                f"<no StockTwits messages found for ${ticker.upper()}>",
                reasons=("EMPTY",),
            )

    lines = []
    bullish = bearish = unlabeled = 0
    for m in _displayed_messages(messages, limit):
        created = m.get("created_at", "")
        user = (m.get("user") or {}).get("username", "?")
        entities = m.get("entities") or {}
        sentiment_obj = entities.get("sentiment") or {}
        sentiment = sentiment_obj.get("basic") if isinstance(sentiment_obj, dict) else None
        body = _body(m).replace("\n", " ").strip()
        if len(body) > 280:
            body = body[:280] + "…"

        if sentiment == "Bullish":
            bullish += 1
            tag = "Bullish"
        elif sentiment == "Bearish":
            bearish += 1
            tag = "Bearish"
        else:
            unlabeled += 1
            tag = "no-label"
        lines.append(f"[{created} · @{user} · {tag}] {body}")

    total = bullish + bearish + unlabeled
    bull_pct = round(100 * bullish / total) if total else 0
    bear_pct = round(100 * bearish / total) if total else 0
    summary = (
        f"Bullish: {bullish} ({bull_pct}%) · "
        f"Bearish: {bearish} ({bear_pct}%) · "
        f"Unlabeled: {unlabeled} · "
        f"Total: {total} most-recent messages"
    )
    return result(
        (f"{note}\n\n" if note else "") + summary + "\n\n" + "\n".join(lines),
        items=tuple(
            _message_meta(m, ticker) for m in _displayed_messages(messages, limit)
        ),
    )
