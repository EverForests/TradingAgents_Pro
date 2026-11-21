"""Deterministic market-data verification snapshot.

The market analyst is an LLM that can confabulate exact numbers — citing a
Bollinger band or a "historically validated bounce" that the underlying data
doesn't support (#830). This module computes a ground-truth snapshot (latest
OHLCV row on or before the analysis date, common indicators, recent closes)
the analyst is told to treat as the source of truth for any exact numeric
claim. Deterministic, no LLM involved.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable

import pandas as pd
from stockstats import wrap

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.common import price_text
from tradingagents.dataflows.vendors.yahoo.ohlcv import load_ohlcv

# A fixed, common indicator set so the snapshot is the same shape every run.
DEFAULT_SNAPSHOT_INDICATORS: tuple[str, ...] = (
    "close_10_ema", "close_50_sma", "close_200_sma",
    "rsi", "boll", "boll_ub", "boll_lb",
    "macd", "macds", "macdh", "atr",
)

# A stated currency is accepted exactly as the vendor wrote it: a three-letter
# code in capitals (USD, HKD) or a case-significant quote unit (GBp, ZAc).
# Missing markers, digits and other prose are not a currency and never become
# one by default.
_MISSING_CURRENCY = {"", "nan", "none", "null", "n/a", "na", "unknown", "-"}
_QUOTE_UNITS = {"GBp", "ZAc", "ILA", "ILs"}


def _is_quote_currency(value) -> bool:
    """Whether ``value`` names a currency the way the price vendor stated it."""
    if not isinstance(value, str):
        return False
    if value.strip().lower() in _MISSING_CURRENCY:
        return False
    if value in _QUOTE_UNITS:
        return True
    return len(value) == 3 and value.isascii() and value.isalpha() and value.isupper()


def _verified_rows(symbol: str, as_of_date: str) -> pd.DataFrame:
    """OHLCV on or before as_of_date, date-sorted. Raises NoMarketDataError if nothing usable.

    ``load_ohlcv`` already normalizes the Date column and filters out
    look-ahead rows, but we re-apply the cutoff defensively — this is a
    verification path, so it must not trust its input to be pre-filtered.
    """
    # As reported: this snapshot is quoted by the agents as exact prices, so a
    # gap-filled cell would put the previous session's number under this date.
    data = load_ohlcv(symbol, as_of_date, fill_gaps=False)
    if data is None or data.empty:
        raise NoMarketDataError(symbol, normalize_symbol(symbol), "no price rows")

    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df = df[df["Date"] <= pd.to_datetime(as_of_date)].sort_values("Date")
    if df.empty:
        raise NoMarketDataError(symbol, normalize_symbol(symbol), f"no price rows on or before {as_of_date}")
    return df


def _fmt(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        return price_text(value)
    return str(value)


def build_verified_market_snapshot(
    symbol: str,
    as_of_date: str,
    look_back_days: int = 30,
    indicators: Iterable[str] | None = None,
) -> str:
    """Render a ground-truth snapshot: latest OHLCV row, indicators, recent closes."""
    # `df` keeps the original capitalized OHLCV columns (Open/High/Low/Close/
    # Volume); stockstats `wrap()` lowercases columns and adds indicator
    # columns, so read raw prices from `df` and indicators from `stock_df`.
    df = _verified_rows(symbol, as_of_date)
    stock_df = wrap(df.copy())

    selected = tuple(indicators or DEFAULT_SNAPSHOT_INDICATORS)
    indicator_values: dict[str, str] = {}
    for name in selected:
        try:
            stock_df[name]  # triggers stockstats calculation
            indicator_values[name] = _fmt(stock_df.iloc[-1][name])
        except Exception as exc:  # noqa: BLE001 — one bad indicator shouldn't sink the snapshot
            indicator_values[name] = f"N/A ({type(exc).__name__})"

    latest = df.iloc[-1]
    latest_date = _fmt(latest["Date"])
    window = max(1, min(int(look_back_days), 30))
    recent = df.tail(window)

    lines = [
        f"## Verified market data snapshot for {symbol.upper()}",
        "",
        f"- Requested analysis date: {as_of_date}",
        f"- Latest trading row used: {latest_date}",
        "- Rows after the requested analysis date are excluded before verification.",
        "",
        "### Latest verified OHLCV row",
        "",
        "| Field | Value |",
        "|---|---:|",
    ]
    for field in ("Open", "High", "Low", "Close", "Volume"):
        lines.append(f"| {field} | {_fmt(latest.get(field))} |")

    lines += ["", "### Verified technical indicators (latest row)", "",
              "| Indicator | Value |", "|---|---:|"]
    for name, value in indicator_values.items():
        lines.append(f"| {name} | {value} |")

    lines += ["", f"### Recent verified closes (last {len(recent)} rows)", "",
              "| Date | Close |", "|---|---:|"]
    for _, row in recent.iterrows():
        lines.append(f"| {_fmt(row['Date'])} | {_fmt(row.get('Close'))} |")

    lines += [
        "",
        "Use this snapshot as the source of truth for exact OHLCV, price-level, "
        "and indicator-value claims. If another tool output conflicts with it, "
        "flag the discrepancy rather than inventing a reconciled number. Do not "
        "claim historical validation, support/resistance bounces, or exact "
        "percentage moves unless directly supported by tool output with concrete "
        "dates and prices.",
    ]
    # The quote source follows the snapshot as one comment line: the stock and
    # the trading day this row is for, the currency it is priced in, and the two
    # raw figures the text above only renders. It is added only when the frame's
    # own source agrees with this row and both figures are real numbers; a
    # missing, stale, conflicting or non-numeric input returns the snapshot
    # exactly as it was, rather than a source borrowed from elsewhere.
    if _quote_source_is_usable(df, stock_df, symbol, as_of_date, latest, latest_date,
                               selected, indicator_values):
        source = df.attrs.get("fr02_quote_source")
        quote = {
            "symbol": normalize_symbol(symbol),
            "trading_date": latest_date,
            "as_of_date": as_of_date,
            "currency": source["currency"],
            "close": float(latest["Close"]),
            "boll_ub": float(stock_df["boll_ub"].iloc[-1]),
        }
        lines.append("# FR02_QUOTE_SOURCE " + json.dumps(quote, separators=(",", ":")))
    return "\n".join(lines)


def _quote_source_is_usable(df: pd.DataFrame, stock_df: pd.DataFrame, symbol: str,
                            as_of_date: str, latest, latest_date: str,
                            selected: tuple[str, ...], indicator_values: dict) -> bool:
    """Whether this snapshot row carries a source that can be published as is.

    The stock must be the one asked for, the trading day the one this row
    reports, and the currency stated the way the price vendor states one. The
    upper band is read only when it was actually requested and its calculation
    reported no error — the loop records a failure as "N/A" or "N/A (...)", so a
    key on its own proves nothing — and a column stockstats happened to produce
    while computing another band is never cited. Both figures must then be
    finite non-boolean numbers; anything else leaves the snapshot unchanged.
    """
    source = getattr(df, "attrs", {}).get("fr02_quote_source")
    if not isinstance(source, dict) or df.empty or stock_df.empty:
        return False
    if "boll_ub" not in selected:
        return False
    shown = indicator_values.get("boll_ub")
    if not isinstance(shown, str) or not shown.strip() or shown.strip().startswith("N/A"):
        return False
    if "boll_ub" not in stock_df.columns or "Close" not in df.columns:
        return False
    stated = source.get("symbol")
    if not isinstance(stated, str) or stated.strip().upper() != normalize_symbol(symbol).strip().upper():
        return False
    if not isinstance(latest_date, str):
        return False
    if source.get("latest_trading_date") != latest_date:
        return False
    if not _is_quote_currency(source.get("currency")):
        return False
    for value in (latest.get("Close"), stock_df["boll_ub"].iloc[-1]):
        if value is None or pd.api.types.is_bool(value):
            return False
        try:
            if not math.isfinite(float(value)):
                return False
        except (TypeError, ValueError):
            return False
    return True
