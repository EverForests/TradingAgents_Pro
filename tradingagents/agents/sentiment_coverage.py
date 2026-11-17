"""FR-03 sentiment source coverage: deterministic accounting for sentiment.

Three logical sources -- ``news``, ``stocktwits`` and ``reddit`` (whose
subreddits count as one) -- feed the Sentiment Analyst. The model reads only
validated source content and may never widen coverage: this module decides what
counts as evidence, how much of the three-source universe it covers, and
whether a model assessment may become a measured score.

The pieces follow the C3 contract:

* ``normalize_source`` turns one collection result into a SourceOutcome bound to
  the current run (ticker, window and identity all checked).
* ``build_sentiment_coverage`` counts the three logical sources once each.
* ``finalize_sentiment`` keeps coverage authoritative -- the model can only
  downgrade to ``UNKNOWN``/``null``, never impute a band or score.

All records are JSON-compatible dictionaries with deterministic list order, so
a rendered report, a CLI view and a saved artifact can agree.
"""

from __future__ import annotations

import copy
import math
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from tradingagents.dataflows.source_receipt import ItemMeta, SourceReceipt, SourceText
from tradingagents.dataflows.symbols import normalize_symbol

CONTRACT_VERSION = "1.0"

SOURCE_IDS: tuple[str, ...] = ("news", "stocktwits", "reddit")

# Reasons a source fails to contribute evidence. Unknown metadata stays
# distinct from an empty answer and from a vendor that did not respond.
EMPTY = "EMPTY"
FETCH_ERROR = "FETCH_ERROR"
WINDOW_UNSUPPORTED = "WINDOW_UNSUPPORTED"
OUT_OF_WINDOW = "OUT_OF_WINDOW"
TICKER_MISMATCH = "TICKER_MISMATCH"
UNVERIFIABLE_METADATA = "UNVERIFIABLE_METADATA"
NOT_COLLECTED = "NOT_COLLECTED"
SOURCE_ID_MISMATCH = "SOURCE_ID_MISMATCH"
IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
# Assessment-side codes: the coverage was fine, the model's answer was not.
ASSESSMENT_FAILED = "ASSESSMENT_FAILED"
SCORE_INVALID = "SCORE_INVALID"

# Fixed order keeps reason lists deterministic across runs.
_REASON_ORDER: tuple[str, ...] = (
    EMPTY,
    FETCH_ERROR,
    OUT_OF_WINDOW,
    UNVERIFIABLE_METADATA,
    WINDOW_UNSUPPORTED,
    TICKER_MISMATCH,
    SOURCE_ID_MISMATCH,
    IDENTITY_MISMATCH,
    NOT_COLLECTED,
)

_UNVERIFIABLE = "UNVERIFIABLE_METADATA"

# Anchored placeholders the adapters return: the whole text says the fetch
# failed, or that there is nothing to report. A word inside a real headline or
# post is never a placeholder, so only anchored matches classify the source.
_ERROR_PLACEHOLDERS: tuple[re.Pattern, ...] = (
    re.compile(r"^<[a-z_]+ unavailable:[^>]*>$", re.IGNORECASE),
    re.compile(r"^<unavailable>$", re.IGNORECASE),
    re.compile(r"^<reddit unavailable:[^>]*>$", re.IGNORECASE),
    re.compile(r"^data_unavailable:", re.IGNORECASE),
    re.compile(r"^<fetch_error[^>]*>$", re.IGNORECASE),
)
# A feed that cannot reach the requested window says so, anchored to the window.
_WINDOW_PLACEHOLDERS: tuple[re.Pattern, ...] = (
    re.compile(r"^<[^<>]* unavailable for \d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2}[^<>]*>$",
               re.IGNORECASE),
    re.compile(r"^<[^<>]* window unsupported[^<>]*>$", re.IGNORECASE),
)
_EMPTY_PLACEHOLDERS: tuple[re.Pattern, ...] = (
    re.compile(r"^<no [^<>]*>$", re.IGNORECASE),
    # Yahoo's whole empty-result sentence only: a genuine headline that happens
    # to begin "No ... found ..." is real content, not a placeholder.
    re.compile(
        r"^no news found for [^<>]+? between \d{4}-\d{2}-\d{2} and \d{4}-\d{2}-\d{2}\.?$",
        re.IGNORECASE,
    ),
)

_MEASURED_BANDS: tuple[str, ...] = (
    "Bullish",
    "Mildly Bullish",
    "Neutral",
    "Mixed",
    "Mildly Bearish",
    "Bearish",
)
_AFFIRMATIVE_CONFIDENCE: tuple[str, ...] = ("low", "medium", "high")

UNKNOWN_BAND = "UNKNOWN"
MEASURED = "MEASURED"
UNKNOWN = "UNKNOWN"
NO_DATA = "NO_DATA"
PARTIAL_DATA = "PARTIAL_DATA"
AVAILABLE = "AVAILABLE"

_OUTCOME_FIELDS: tuple[str, ...] = (
    "contract_version",
    "run_id",
    "ticker",
    "as_of_date",
    "source_id",
    "window_start",
    "window_end",
    "available",
    "valid_record_count",
    "reason_codes",
    "evidence_refs",
)


# ---------------------------------------------------------------------------
# Identity and window helpers
# ---------------------------------------------------------------------------


def _identity(run: Any) -> dict[str, str]:
    """The run's identity fields, or an empty mapping when the run is unusable."""
    if not isinstance(run, dict):
        return {}
    fields = {}
    for key in ("run_id", "ticker", "as_of_date"):
        value = run.get(key)
        fields[key] = value if isinstance(value, str) else ""
    return fields


def _has_identity(identity: dict[str, str]) -> bool:
    """Whether every identity field is a non-blank string.

    A blank field is not an identity: two records that share blanks must never
    accept each other, so blanks are rejected rather than stripped or matched.
    """
    return all(
        isinstance(identity.get(key), str) and identity[key].strip()
        for key in ("run_id", "ticker", "as_of_date")
    )


def _same_identity(left: dict[str, str], right: dict[str, str]) -> bool:
    if not (_has_identity(left) and _has_identity(right)):
        return False
    return all(left[key] == right[key] for key in ("run_id", "ticker", "as_of_date"))


def _parse_day(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _baseline_window(run: dict[str, str]) -> tuple[date, date] | None:
    """The baseline sentiment window: seven days back through the as-of date."""
    as_of = _parse_day(run.get("as_of_date", ""))
    if as_of is None:
        return None
    return as_of - timedelta(days=7), as_of


def _is_baseline_window(run: dict[str, str], window_start: Any, window_end: Any) -> bool:
    """Whether ``(window_start, window_end)`` is exactly the run's baseline window."""
    baseline = _baseline_window(run)
    if baseline is None:
        return False
    return (_parse_day(window_start), _parse_day(window_end)) == baseline


def _window_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """Half-open UTC bounds: [start 00:00 UTC, end + 1 day 00:00 UTC)."""
    return (
        datetime(start.year, start.month, start.day, tzinfo=UTC),
        datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1),
    )


def _in_window(published_at: datetime | None, start: date, end: date) -> bool:
    if not isinstance(published_at, datetime):
        return False
    if published_at.tzinfo is None or published_at.utcoffset() is None:
        return False
    lower, upper = _window_bounds(start, end)
    when = published_at.astimezone(UTC)
    return lower <= when < upper


# ---------------------------------------------------------------------------
# Source normalization
# ---------------------------------------------------------------------------


def _ordered_reasons(reasons: set[str]) -> list[str]:
    known = [reason for reason in _REASON_ORDER if reason in reasons]
    extra = sorted(reason for reason in reasons if reason not in _REASON_ORDER)
    return known + extra


def _valid_reason_list(value: Any) -> bool:
    """Whether ``value`` is a list/tuple of non-blank strings."""
    return isinstance(value, (list, tuple)) and all(
        isinstance(code, str) and code.strip() for code in value
    )


def _adapter_reasons(receipt: SourceReceipt) -> set[str]:
    """Receipt reason codes the adapter reported, mapped to known vocabulary.

    Reasons are additive: a valid item keeps the source available even when the
    adapter also reports a failed item. Malformed containers are rejected by
    ``normalize_source`` before this runs.
    """
    found: set[str] = set()
    for code in receipt.reason_codes:
        normalized = code.strip().upper()
        if normalized in _REASON_ORDER:
            found.add(normalized)
        elif "ERROR" in normalized or "UNAVAILABLE" in normalized:
            found.add(FETCH_ERROR)
        else:
            found.add(UNVERIFIABLE_METADATA)
    return found


def _placeholder_reason(text: str) -> str | None:
    """EMPTY/FETCH_ERROR/WINDOW_UNSUPPORTED when the whole text is an anchored placeholder."""
    stripped = text.strip()
    if not stripped:
        return EMPTY
    if any(pattern.match(stripped) for pattern in _WINDOW_PLACEHOLDERS):
        return WINDOW_UNSUPPORTED
    if any(pattern.match(stripped) for pattern in _ERROR_PLACEHOLDERS):
        return FETCH_ERROR
    if any(pattern.match(stripped) for pattern in _EMPTY_PLACEHOLDERS):
        return EMPTY
    return None


def _evidence_ref(source_id: str, vendor: str, item: ItemMeta) -> str:
    """A shareable locator for one counted item: source, vendor and item id only."""
    return f"{source_id}/{vendor or 'unknown'}:{item.item_id}"


def _same_ticker(reported: Any, run_ticker: str) -> bool:
    """Whether a reported ticker is attributable to the run's ticker.

    Both sides must be non-blank strings and must agree as the canonical symbols
    the vendors use, so a raw ``aapl`` receipt binds to an ``AAPL`` run and
    ``BTCUSD`` to ``BTC-USD``. Anything blank or unreadable never matches; the
    run's own identity fields stay compared exactly elsewhere.
    """
    if not (isinstance(reported, str) and reported.strip()):
        return False
    if not (isinstance(run_ticker, str) and run_ticker.strip()):
        return False
    return normalize_symbol(reported) == normalize_symbol(run_ticker)


def news_vendor(raw_result: Any) -> str:
    """The vendor that actually answered a news collection, or ``unknown``.

    The prompt and the evidence refs label the real vendor, so an Alpha Vantage
    answer is never presented as Yahoo Finance.
    """
    receipt = getattr(raw_result, "source_receipt", None)
    vendor = getattr(receipt, "vendor", None)
    return vendor if isinstance(vendor, str) and vendor else "unknown"


def _unavailable_outcome(identity: dict[str, str], source_id: str,
                         window_start: Any, window_end: Any,
                         reasons: set[str]) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": identity.get("run_id", ""),
        "ticker": identity.get("ticker", ""),
        "as_of_date": identity.get("as_of_date", ""),
        "source_id": source_id,
        "window_start": window_start,
        "window_end": window_end,
        "available": False,
        "valid_record_count": 0,
        "reason_codes": _ordered_reasons(reasons),
        "evidence_refs": [],
    }


def normalize_source(raw_result: Any, source_id: str, run: Any,
                     window_start: Any, window_end: Any) -> dict[str, Any]:
    """Derive one run-bound SourceOutcome from a collection result.

    Only a ``SourceText`` carries a request-bound receipt. The receipt must name
    ``source_id``, the run's ticker and the requested window, and every item
    must be timestamped in the window, attributable to the ticker and
    substantive. A plain string -- however long -- proves nothing about what the
    source returned, so it can never make a source available; an empty or
    anchored placeholder still says why it has nothing. Reasons are additive: a
    source with some valid items and some rejected ones keeps counting.
    """
    identity = _identity(run)
    reasons: set[str] = set()
    text = str(raw_result) if isinstance(raw_result, str) else ""

    if not _has_identity(identity):
        # A blank run identity cannot bind any record: nothing blank is accepted.
        reasons.add(IDENTITY_MISMATCH)
        return _unavailable_outcome(identity, source_id, window_start, window_end, reasons)

    if not isinstance(raw_result, SourceText):
        # Distinguish an actual empty answer or adapter placeholder from opaque
        # content before rejecting it: the placeholder is anchored and exact,
        # never a word that happens to appear inside legitimate text.
        reasons.add(_placeholder_reason(text) or UNVERIFIABLE_METADATA)
        return _unavailable_outcome(identity, source_id, window_start, window_end, reasons)

    receipt = getattr(raw_result, "source_receipt", None)
    if not isinstance(receipt, SourceReceipt):
        reasons.add(_placeholder_reason(text) or UNVERIFIABLE_METADATA)
        return _unavailable_outcome(identity, source_id, window_start, window_end, reasons)

    if receipt.source_id != source_id:
        reasons.add(SOURCE_ID_MISMATCH)
        return _unavailable_outcome(identity, source_id, window_start, window_end, reasons)

    if not isinstance(receipt.items, (list, tuple)) or not _valid_reason_list(receipt.reason_codes):
        # A malformed container is unverifiable data, never a crash.
        reasons.add(UNVERIFIABLE_METADATA)
        return _unavailable_outcome(identity, source_id, window_start, window_end, reasons)

    reasons |= _adapter_reasons(receipt)

    request_ok = _is_baseline_window(identity, window_start, window_end)
    receipt_ok = _is_baseline_window(identity, receipt.window_start, receipt.window_end)
    if not request_ok or not receipt_ok:
        reasons.add(WINDOW_UNSUPPORTED)
        return _unavailable_outcome(
            identity, source_id, receipt.window_start, receipt.window_end, reasons
        )

    if not _same_ticker(receipt.ticker, identity.get("ticker", "")):
        reasons.add(TICKER_MISMATCH)
        return _unavailable_outcome(
            identity, source_id, receipt.window_start, receipt.window_end, reasons
        )

    if not receipt.items:
        # Nothing collected: the placeholder says why (an error or an empty answer).
        reasons.add(_placeholder_reason(text) or EMPTY)
        return _unavailable_outcome(
            identity, source_id, receipt.window_start, receipt.window_end, reasons
        )

    # A receipt can carry valid metadata while the body itself is blank or an
    # anchored placeholder: the body then contradicts the metadata it claims.
    body_reason = _placeholder_reason(text)
    if body_reason is not None:
        reasons.add(body_reason)
        return _unavailable_outcome(
            identity, source_id, receipt.window_start, receipt.window_end, reasons
        )

    ticker = identity.get("ticker", "")
    start, end = _baseline_window(identity)
    evidence_refs: list[str] = []
    for item in receipt.items:
        if not isinstance(item, ItemMeta):
            reasons.add(UNVERIFIABLE_METADATA)
            continue
        if not isinstance(item.item_id, str) or not item.item_id.strip():
            reasons.add(UNVERIFIABLE_METADATA)
            continue
        if item.substantive is not True:
            # Only an explicit True is substantive: 1 and "false" are not.
            reasons.add(UNVERIFIABLE_METADATA)
            continue
        if item.ticker is not None and not _same_ticker(item.ticker, ticker):
            reasons.add(TICKER_MISMATCH)
            continue
        if item.published_at is None:
            reasons.add(UNVERIFIABLE_METADATA)
            continue
        if not _in_window(item.published_at, start, end):
            reasons.add(OUT_OF_WINDOW)
            continue
        ref = _evidence_ref(source_id, receipt.vendor, item)
        if ref not in evidence_refs:
            evidence_refs.append(ref)

    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": identity.get("run_id", ""),
        "ticker": ticker,
        "as_of_date": identity.get("as_of_date", ""),
        "source_id": source_id,
        "window_start": receipt.window_start,
        "window_end": receipt.window_end,
        "available": bool(evidence_refs),
        "valid_record_count": len(evidence_refs),
        "reason_codes": _ordered_reasons(reasons),
        "evidence_refs": evidence_refs,
    }


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------


def _safe_reasons(value: Any) -> set[str]:
    """Only the safe, well-formed reason strings carried by a record.

    A malformed field (an int, a list of lists, ...) contributes nothing, so a
    rejected copy never crashes and never copies invalid data through.
    """
    if not _valid_reason_list(value):
        return set()
    return set(value)


def _window_field(outcome: dict[str, Any], key: str) -> Any:
    """A window field as plain data, so a rejected copy stays JSON-shaped."""
    value = outcome.get(key)
    return value if isinstance(value, str) else None


def _rejected_outcome(outcome: dict[str, Any], identity: dict[str, str],
                      reasons: set[str]) -> dict[str, Any]:
    """A copy of ``outcome`` marked unavailable for the current run.

    The input is never modified: the caller keeps its own record intact, and
    the coverage mapping holds an unavailable copy with an explicit reason
    instead of silently dropping a source that claimed evidence. The copy always
    has the standard C3 fields for the current identity: only safe reason strings
    survive, plus the rejection reason.
    """
    return _unavailable_outcome(
        identity, str(outcome.get("source_id") or ""),
        _window_field(outcome, "window_start"), _window_field(outcome, "window_end"),
        _safe_reasons(outcome.get("reason_codes")) | reasons,
    )


def _accepted_outcome(outcome: dict[str, Any], identity: dict[str, str],
                      window_start: Any, window_end: Any) -> dict[str, Any]:
    """The outcome as it may stand for the current run, or a rejected copy."""
    reject = _rejected_outcome(outcome, identity, {UNVERIFIABLE_METADATA})
    if set(outcome) != set(_OUTCOME_FIELDS):
        return reject
    if not _has_identity(identity):
        return reject
    if outcome.get("contract_version") != CONTRACT_VERSION:
        return reject
    if not isinstance(outcome.get("available"), bool):
        return reject
    if not _valid_reason_list(outcome.get("reason_codes")):
        return reject
    refs = outcome.get("evidence_refs")
    if not (isinstance(refs, list)
            and all(isinstance(ref, str) and ref.strip() for ref in refs)):
        return reject

    outcome_identity = {
        key: str(outcome.get(key) or "") for key in ("run_id", "ticker", "as_of_date")
    }
    if not _same_identity(outcome_identity, identity):
        return _rejected_outcome(outcome, identity, {IDENTITY_MISMATCH})

    outcome_window = (_parse_day(outcome.get("window_start")), _parse_day(outcome.get("window_end")))
    accepted_window = (_parse_day(window_start), _parse_day(window_end))
    if None in outcome_window or outcome_window != accepted_window:
        return _rejected_outcome(outcome, identity, {WINDOW_UNSUPPORTED})

    count = outcome.get("valid_record_count")
    consistent = (
        len(refs) == len(set(refs))
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count >= 0
        and count == len(refs)
    )
    if not consistent or outcome["available"] != (count > 0):
        return reject
    if count == 0:
        return _rejected_outcome(outcome, identity, {EMPTY})
    return outcome


def build_sentiment_coverage(sources: Any, run: Any) -> dict[str, Any]:
    """Count the three logical sources once each and report coverage.

    Inputs are normalized SourceOutcomes for ``run``; the window is the run's
    own baseline window (as-of date minus seven days through the as-of date), so
    the boundary needs no caller-supplied dates. One that belongs to another
    run, or that no longer matches this run's ticker, window or shape, is copied
    as unavailable with an identity reason: it never counts. The first outcome
    wins for a source, so duplicate collections of one source cannot overcount.
    A source with no outcome is reported as NOT_COLLECTED rather than
    disappearing from the denominator. Input records are not modified.
    """
    identity = _identity(run)
    baseline = _baseline_window(identity)
    window_start = baseline[0].isoformat() if baseline else None
    window_end = baseline[1].isoformat() if baseline else None

    entries: dict[str, dict[str, Any]] = {}
    for outcome in sources or ():
        if not isinstance(outcome, dict):
            continue
        source_id = outcome.get("source_id")
        if source_id not in SOURCE_IDS or source_id in entries:
            continue
        entries[source_id] = _accepted_outcome(outcome, identity, window_start, window_end)

    coverage_sources: dict[str, dict[str, Any]] = {}
    for source_id in SOURCE_IDS:
        entry = entries.get(source_id)
        if entry is None:
            coverage_sources[source_id] = _unavailable_outcome(
                identity, source_id, window_start, window_end, {NOT_COLLECTED}
            )
            continue
        coverage_sources[source_id] = {
            "contract_version": CONTRACT_VERSION,
            "run_id": identity.get("run_id", ""),
            "ticker": identity.get("ticker", ""),
            "as_of_date": identity.get("as_of_date", ""),
            "source_id": source_id,
            "window_start": entry.get("window_start"),
            "window_end": entry.get("window_end"),
            "available": bool(entry.get("available")),
            "valid_record_count": int(entry.get("valid_record_count") or 0),
            "reason_codes": list(entry.get("reason_codes") or []),
            "evidence_refs": list(entry.get("evidence_refs") or []),
        }

    valid = sum(1 for entry in coverage_sources.values() if entry["available"])
    if valid == 0:
        status = NO_DATA
    elif valid < len(SOURCE_IDS):
        status = PARTIAL_DATA
    else:
        status = AVAILABLE

    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": identity.get("run_id", ""),
        "ticker": identity.get("ticker", ""),
        "as_of_date": identity.get("as_of_date", ""),
        "coverage_status": status,
        "valid_sources": valid,
        "total_sources": len(SOURCE_IDS),
        "sources": coverage_sources,
    }


# ---------------------------------------------------------------------------
# Finalization: coverage is authoritative, the model can only downgrade
# ---------------------------------------------------------------------------


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _measured_score(value: Any) -> float | None:
    """A finite 0-10 score, or None. Booleans and strings are not measurements."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    # Compare in the value's own type first: an int far outside 0-10 is rejected
    # without a float conversion, which would overflow for huge integers.
    if value < 0 or value > 10:
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or number > 10.0:
        return None
    return number


def _assessment_fields(assessment: Any) -> dict[str, Any]:
    """Read band/score/confidence/narrative from a report or a plain mapping."""
    read = assessment.get if isinstance(assessment, dict) else (
        lambda key: getattr(assessment, key, None)
    )
    band = read("overall_band")
    band_value = getattr(band, "value", band)
    return {
        "band": _text(band_value),
        "score": _measured_score(read("overall_score")),
        "confidence": _text(read("confidence")).lower(),
        "narrative": _text(read("narrative")),
    }


def _coverage_reason_summary(coverage: dict[str, Any]) -> list[str]:
    summaries = []
    for source_id in SOURCE_IDS:
        entry = coverage.get("sources", {}).get(source_id, {})
        reasons = ",".join(entry.get("reason_codes") or []) or "none"
        state = "available" if entry.get("available") else "unavailable"
        summaries.append(f"{source_id}: {state} ({reasons})")
    return summaries


def _missing_statement(coverage: dict[str, Any], reason: str) -> str:
    """Concise deterministic text for an UNKNOWN assessment; model prose is never reused.

    Only the description lives here: the header is rendered once by the report
    renderer from the same record.
    """
    valid = int(coverage.get("valid_sources") or 0)
    total = int(coverage.get("total_sources") or len(SOURCE_IDS))
    lines = [
        f"No measured sentiment ({reason}): this is a data-coverage statement, not "
        "a Neutral reading, and no score is imputed.",
        "",
        f"Source coverage: {valid}/{total} ({coverage.get('coverage_status')}).",
    ]
    lines.extend(f"- {summary}" for summary in _coverage_reason_summary(coverage))
    return "\n".join(lines)


def _assessment_failure_reason(assessment: Any) -> str:
    """ASSESSMENT_FAILED when no usable assessment, SCORE_INVALID for a bad score."""
    if assessment is None:
        return ASSESSMENT_FAILED
    fields = _assessment_fields(assessment)
    if fields["score"] is None:
        return SCORE_INVALID
    return ASSESSMENT_FAILED


def _copy_coverage(coverage: dict[str, Any]) -> dict[str, Any]:
    """A deep copy of the coverage record, so no nested list is shared."""
    return copy.deepcopy(coverage)


def finalize_sentiment(coverage: dict[str, Any], model_assessment_or_null: Any,
                       run: Any) -> dict[str, Any]:
    """Combine authoritative coverage with an optional model assessment.

    With zero valid sources the result is UNKNOWN/null without consulting the
    model at all. With valid sources, a measured result needs a valid band, a
    finite 0-10 score and a known confidence; anything missing or invalid
    downgrades to UNKNOWN/null while the actual coverage is preserved verbatim
    and the reason code says which check failed. Model narrative survives only
    for a measured result; an UNKNOWN result carries deterministic text
    instead, so no model prose can contradict the data statement. Coverage from
    another run is rejected outright: it is never relabelled as this run's.
    """
    coverage = coverage if isinstance(coverage, dict) else {}
    identity = _identity(run)
    coverage_identity = {key: str(coverage.get(key) or "") for key in identity}
    if coverage and not _same_identity(coverage_identity, identity):
        raise ValueError("sentiment coverage does not belong to this run")

    result = _copy_coverage(coverage)
    result.update({
        "contract_version": CONTRACT_VERSION,
        "run_id": identity.get("run_id", ""),
        "ticker": identity.get("ticker", ""),
        "as_of_date": identity.get("as_of_date", ""),
        "coverage_status": coverage.get("coverage_status", NO_DATA),
        "valid_sources": int(coverage.get("valid_sources") or 0),
        "total_sources": int(coverage.get("total_sources") or len(SOURCE_IDS)),
    })

    def _unknown(reason: str) -> dict[str, Any]:
        record = dict(result)
        record.update({
            "assessment_status": UNKNOWN,
            "overall_band": UNKNOWN_BAND,
            "overall_score": None,
            "confidence": "low",
            "assessment_reason_codes": [reason],
            "narrative": _missing_statement(result, reason),
        })
        return record

    if result["valid_sources"] == 0:
        return _unknown(EMPTY)

    fields = _assessment_fields(model_assessment_or_null)
    if (
        fields["band"] not in _MEASURED_BANDS
        or fields["score"] is None
        or fields["confidence"] not in _AFFIRMATIVE_CONFIDENCE
        or not fields["narrative"]
    ):
        return _unknown(_assessment_failure_reason(model_assessment_or_null))

    measured = dict(result)
    measured.update({
        "assessment_status": MEASURED,
        "overall_band": fields["band"],
        "overall_score": fields["score"],
        "confidence": fields["confidence"],
        "assessment_reason_codes": [],
        "narrative": fields["narrative"],
    })
    return measured
