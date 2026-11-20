import logging
import os

import pandas as pd
import yfinance as yf

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.files import replace_file
from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component
from tradingagents.dataflows.vendors.yahoo.common import raise_for_empty, yf_retry

logger = logging.getLogger(__name__)

# A vendor's latest OHLCV row this many calendar days before the requested date
# is treated as stale. Generous enough to span long holiday weekends, tight
# enough to catch the year-old frames yfinance occasionally returns (#1021).
MAX_OHLCV_STALE_DAYS = 10

# How long a same-day cache that does not yet reach the requested day may be
# reused before it is refetched (#1150). Short enough that an intraday run picks
# up today's close soon after it publishes, long enough that a day with no bar
# at all (weekend, holiday) cannot trigger a download on every call.
OHLCV_CACHE_TTL_SECONDS = 900


def _ensure_date_column(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize the date column to ``Date``.

    Some yfinance builds leave the index unnamed (so ``reset_index()`` yields
    ``index``) or use ``Datetime`` for intraday data. Rename the first
    date-like column so indicators don't silently drop when it isn't ``Date``.
    """
    if "Date" in data.columns:
        return data
    for candidate in ("index", "Datetime", "date"):
        if candidate in data.columns:
            return data.rename(columns={candidate: "Date"})
    return data


def _local_midnight(value) -> pd.Timestamp:
    """A single timestamp as its naive, midnight-normalized local date (or NaT)."""
    if pd.isna(value):
        return pd.NaT
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return pd.NaT
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)  # drop tz, keep the local wall-clock date
    return ts.normalize()


def _normalize_dates(dates) -> pd.Series:
    """Parse to naive, midnight-normalized dates so tz-aware or intraday
    timestamps compare correctly against the naive ``as_of_date`` cutoff (#1201).

    Normalized per element: 5 years of yfinance bars span daylight-saving
    changes (and cache CSVs round-trip the offsets as strings), so the series can
    carry mixed UTC offsets that ``pd.to_datetime`` cannot unify without
    ``utc=True`` — which would shift non-US (positive-offset) markets to the
    previous day. Keeping each bar's own local date avoids both.
    """
    return pd.to_datetime(pd.Series(dates).map(_local_midnight))


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize a stock DataFrame for stockstats: parse/normalize dates and
    coerce prices to numeric (NaN where invalid). Dropping incomplete rows and
    filling gaps is left to ``_fill_price_gaps`` so the caller can first inspect
    the latest in-range bar (#1201)."""
    data = _ensure_date_column(data)
    data["Date"] = _normalize_dates(data["Date"])
    data = data.dropna(subset=["Date"]).copy()

    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    return data


def _fill_price_gaps(data: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with no close and forward/back-fill remaining price gaps so
    indicators compute on a continuous series."""
    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    # copy() so a filtered (sliced) input is written to safely, not via a view.
    data = data.dropna(subset=["Close"]).copy()
    data[price_cols] = data[price_cols].ffill().bfill()
    return data


def _coerce_ohlcv_dates(data: pd.DataFrame) -> pd.Series:
    """Return parsed dates from an OHLCV frame, whether Date is a column or the index."""
    if "Date" in data.columns:
        return pd.to_datetime(data["Date"], errors="coerce").dropna()
    # yfinance keeps the dates in the index (a DatetimeIndex, sometimes unnamed).
    if isinstance(data.index, pd.DatetimeIndex):
        return pd.Series(pd.to_datetime(data.index, errors="coerce")).dropna()
    # Fallback: expose the index and look for any date-like column.
    df = data.reset_index()
    for col in ("Date", "Datetime", "date", "index"):
        if col in df.columns:
            parsed = pd.to_datetime(df[col], errors="coerce").dropna()
            if not parsed.empty:
                return parsed
    return pd.Series(dtype="datetime64[ns]")


def _assert_ohlcv_not_stale(
    data: pd.DataFrame,
    as_of_date: str,
    symbol: str,
    canonical: str | None = None,
    *,
    max_stale_days: int = MAX_OHLCV_STALE_DAYS,
) -> None:
    """Reject OHLCV whose latest row is far older than as_of_date.

    Raises NoMarketDataError (with a stale-specific detail) so the router treats
    it like any other "no usable data from this vendor" — try the next vendor,
    then emit one clear unavailable signal. Empty frames are left to the
    caller's existing no-data handling; this guards only the dangerous case of
    present-but-stale rows (a vendor returning a year-old frame that would
    otherwise feed wrong prices to the agent, #1021).
    """
    if data is None or data.empty:
        return
    requested = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(requested):
        return
    requested = requested.normalize()
    dates = _coerce_ohlcv_dates(data)
    if dates.empty:
        return
    latest = dates.max().normalize()
    stale_days = (requested - latest).days
    if stale_days > max_stale_days:
        raise NoMarketDataError(
            symbol,
            canonical,
            f"latest row is {latest.date()}, {stale_days} days before the "
            f"requested {requested.date()} (stale) — refusing to use it",
        )


def _cache_is_fresh(data_file, as_of_dt, now) -> bool:
    """Whether the symbol's cached download can serve this request.

    The file holds the download made on the day it was written, so it serves
    only that day. A current-day request also refetches once the file is older
    than the TTL: Yahoo publishes a partial daily candle during market hours,
    whose ``Close`` is not the closing price, and row inspection cannot tell it
    from a final one (#1150).
    """
    written = pd.Timestamp.fromtimestamp(os.path.getmtime(data_file))
    if written.date() != now.date():
        return False
    return as_of_dt.date() < now.date() or (now - written).total_seconds() <= OHLCV_CACHE_TTL_SECONDS


def load_ohlcv(symbol: str, as_of_date: str, fill_gaps: bool = True) -> pd.DataFrame:
    """Fetch OHLCV data with caching, filtered to prevent look-ahead bias.

    Downloads 5 years of data up to today and caches per symbol. On
    subsequent calls the cache is reused. Rows after as_of_date are
    filtered out so backtests never see future prices.

    ``fill_gaps`` carries prices forward over gaps so indicators compute on a
    continuous series. Pass ``False`` to read the values as the vendor reported
    them, leaving a cell that was never reported empty.
    """
    # Resolve broker/forex symbols (XAUUSD+ -> GC=F) to Yahoo's convention,
    # then reject values that would escape the cache directory when
    # interpolated into the cache filename (e.g. ``../../tmp/x``).
    canonical = normalize_symbol(symbol)
    safe_symbol = safe_ticker_component(canonical)

    config = get_config()
    as_of_dt = pd.to_datetime(as_of_date).normalize()

    # One cache file per symbol, holding the latest 5y-to-today download.
    now = pd.Timestamp.today()
    start_date = now - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    # yfinance ``end`` is EXCLUSIVE; request tomorrow so today's row is included
    # when as_of_date is the current day (#986). Look-ahead is still prevented by
    # the as_of_date filter below.
    end_str = (now + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{safe_symbol}-YFin-data.csv",
    )

    # A cached file may be empty if a prior fetch failed (unknown symbol,
    # transient rate limit). Treat an empty/columnless cache as a miss and
    # re-fetch rather than serving the poisoned file forever.
    data = None
    if os.path.exists(data_file):
        cached = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
        if (
            not cached.empty
            and "Close" in cached.columns
            and _cache_is_fresh(data_file, as_of_dt, now)
        ):
            data = cached

    # The two source columns. A download writes them beside the prices; a cache
    # written before them simply has none, which reads as no evidence rather
    # than as a currency to be filled in later.
    symbol_column = "ohlcv_source_symbol"
    currency_column = "ohlcv_source_currency"

    # A stated currency is taken as the vendor wrote it: a three-letter code in
    # capitals (USD, HKD) or a case-significant quote unit (GBp, ZAc). Missing
    # markers, digits and other prose are not a currency, and nothing is
    # converted — GBp is not turned into GBP.
    _MISSING_MARKERS = {"", "nan", "none", "null", "n/a", "na", "unknown", "-"}
    _QUOTE_UNITS = {"GBp", "ZAc", "ILA", "ILs"}

    def _is_quote_unit(value: str) -> bool:
        if value.strip().lower() in _MISSING_MARKERS:
            return False
        if value in _QUOTE_UNITS:
            return True
        return len(value) == 3 and value.isascii() and value.isalpha() and value.isupper()

    def _metadata(ticker) -> tuple[str, str]:
        """(symbol, currency) from the ticker that served the rows, or ("", "").

        ``get_history_metadata`` is called once; a missing method, a raised
        error, a reply that is not a mapping, or keys that are not plain strings
        each leave the currency unstated. The value is kept exactly as stated —
        no default of USD and no case change, so GBp stays GBp.
        """
        getter = getattr(ticker, "get_history_metadata", None)
        if not callable(getter):
            return "", ""
        try:
            meta = getter()
            if meta is None or not hasattr(meta, "get"):
                return "", ""
            symbol = meta.get("symbol")
            currency = meta.get("currency")
        except Exception:  # a vendor reply is untrusted; no metadata is not a failure
            return "", ""
        if not isinstance(symbol, str) or not isinstance(currency, str):
            return "", ""
        return symbol.strip(), currency

    def _text(value) -> str:
        """A raw cell as a usable string, or "" when it is missing or not text.

        The check comes before any conversion: NaN and None are absences, not
        the strings "nan" and "None".
        """
        if not isinstance(value, str):
            return ""
        return value.strip()

    if data is None:
        # yf.download catches every error, a rate limit included, and returns
        # an empty frame. Ticker.history raises the rate limit, so it is retried.
        # The ticker is built inside each attempt, so the instance that served
        # the rows is the one carried out of the retry with them.
        attempt: dict = {}

        def fetch():
            attempt["ticker"] = yf.Ticker(canonical)
            return attempt["ticker"].history(
                start=start_str,
                end=end_str,
                auto_adjust=True,
                actions=False,
            )

        downloaded = yf_retry(fetch)
        if downloaded is None:
            raise_for_empty(symbol, canonical, "price rows")
        downloaded = _ensure_date_column(downloaded.reset_index())
        # Only cache real data — never persist an empty frame.
        if downloaded.empty or "Close" not in downloaded.columns:
            raise_for_empty(symbol, canonical, "price rows")
        # The stock and currency belong to the ticker that served these rows, so
        # they are read only once rows arrived, and stored beside them.
        source_symbol, source_currency = _metadata(attempt.get("ticker"))
        downloaded[symbol_column] = source_symbol
        downloaded[currency_column] = source_currency
        replace_file(data_file, lambda temp: downloaded.to_csv(temp, index=False, encoding="utf-8"))
        data = downloaded

    # The two source columns ride with the rows they described: through cleaning,
    # the as_of_date filter and the valid-row selection, so every row that takes
    # part in the result still carries its own stock and currency.
    data = _clean_dataframe(data)

    # Filter to as_of_date to prevent look-ahead bias in backtesting.
    data = data[data["Date"] <= as_of_dt]

    # A closeless newest bar is an unsettled session, not a symbol without data.
    # _fill_price_gaps below drops it, here and mid-series alike, so the frame
    # ends at the last settled bar; only a range with no close anywhere is no
    # data (#1201, #1289).
    if not data.empty and pd.isna(data["Close"].iloc[-1]):
        settled = data["Close"].notna().to_numpy().nonzero()[0]
        if settled.size == 0:
            raise NoMarketDataError(
                symbol, canonical, "no bar in range has a closing price"
            )
        logger.warning(
            "%s: %d trailing bar(s) through %s have no closing price; using %s "
            "as the latest close.", canonical, len(data) - settled[-1] - 1,
            data["Date"].iloc[-1].date(), data["Date"].iloc[settled[-1]].date(),
        )

    # Indicators need a continuous series, so gaps are carried forward. A caller
    # that reports the numbers themselves asks for the frame as it was reported:
    # a filled cell is the previous session's price under this session's date.
    data = _fill_price_gaps(data) if fill_gaps else data.dropna(subset=["Close"]).copy()

    # Reject a stale frame (latest row far older than as_of_date) rather than
    # feeding year-old prices into indicators (#1021).
    _assert_ohlcv_not_stale(data, as_of_date, symbol, canonical)

    # The source is decided from the rows that made it into the result, never
    # from the first cache record or from an assumption: every such row must
    # name the stock asked for and one and the same currency, and the trading
    # day is the newest date actually served. Anything else returns the prices
    # as they are with no verifiable source attached.
    source = None
    if not data.empty:
        stocks = {_text(v) for v in data.get(symbol_column, pd.Series(dtype=object))}
        monies = {_text(v) for v in data.get(currency_column, pd.Series(dtype=object))}
        if (len(stocks) == 1 and len(monies) == 1
                and stocks != {""} and monies != {""}
                and next(iter(stocks)).upper() == canonical.strip().upper()
                and _is_quote_unit(next(iter(monies)))):
            source = {
                "symbol": canonical,
                "currency": next(iter(monies)),
                "latest_trading_date": pd.to_datetime(data["Date"]).max().strftime("%Y-%m-%d"),
            }
    data = data.drop(columns=[c for c in (symbol_column, currency_column)
                              if c in data.columns])

    attrs = dict(getattr(data, "attrs", {}))
    attrs.pop("fr02_quote_source", None)
    if source is not None:
        attrs["fr02_quote_source"] = source
    data.attrs = attrs
    return data


