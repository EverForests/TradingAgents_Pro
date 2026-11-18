"""FR-03 coverage: deterministic source accounting (r4 contract).

* ``tradingagents.dataflows.source_receipt`` -- ``SourceText`` / ``SourceReceipt``
  / ``ItemMeta`` (``SourceText`` is a ``str`` subclass; receipts are
  collection-level and carry no ``run_id`` by design).
* ``tradingagents.agents.sentiment_coverage`` -- ``normalize_source`` /
  ``build_sentiment_coverage`` / ``finalize_sentiment`` returning the C3 dicts.

C3 SourceOutcome fields: contract_version, run_id, ticker, as_of_date,
source_id, window_start, window_end, available, valid_record_count,
reason_codes, evidence_refs. Coverage ``sources`` is a mapping keyed by source
id. Unknown output is upper-case ``UNKNOWN`` everywhere.

New-module imports stay inside tests. Fixtures are synthetic.
"""

import datetime
import json

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
SOURCE_IDS = ("news", "stocktwits", "reddit")
HEADLINE = "Synthetic headline: fixture company reports steady quarter"


def _dt(text):
    """UTC datetime from ``YYYY-MM-DD`` or ``YYYY-MM-DD HH:MM``."""
    fmt = "%Y-%m-%d %H:%M" if " " in text else "%Y-%m-%d"
    return datetime.datetime.strptime(text, fmt).replace(tzinfo=datetime.UTC)


def _item(item_id, published_at="2026-11-05", substantive=True, ticker=TICKER):
    from tradingagents.dataflows.source_receipt import ItemMeta

    return ItemMeta(
        item_id=item_id,
        published_at=None if published_at is None else _dt(published_at),
        ticker=ticker,
        substantive=substantive,
    )


def _source_text(source_id, text="fixture", *, ticker=TICKER, start=WINDOW_START,
                 end=WINDOW_END, items=(), reasons=()):
    from tradingagents.dataflows.source_receipt import SourceReceipt, SourceText

    receipt = SourceReceipt(
        source_id=source_id, vendor="fixture_vendor", ticker=ticker,
        window_start=start, window_end=end,
        items=tuple(items), reason_codes=tuple(reasons),
    )
    return SourceText(text, receipt)


def _normalized(source_id, *, text="fixture", run=RUN, **kwargs):
    """A C3 SourceOutcome produced by ``normalize_source`` (not a raw receipt)."""
    from tradingagents.agents.sentiment_coverage import normalize_source

    return normalize_source(
        _source_text(source_id, text, **kwargs), source_id, run, WINDOW_START, WINDOW_END
    )


# ---------------------------------------------------------------------------
# normalize_source
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_outcome_has_exact_c3_fields_and_counts_items():
    normalized = _normalized("news", items=[_item("n1"), _item("n2")])
    assert set(normalized) == {
        "contract_version", "run_id", "ticker", "as_of_date", "source_id",
        "window_start", "window_end", "available", "valid_record_count",
        "reason_codes", "evidence_refs",
    }
    assert normalized["available"] is True
    assert normalized["valid_record_count"] == 2
    assert normalized["reason_codes"] == []
    assert normalized["run_id"] == RUN["run_id"]


@pytest.mark.unit
def test_window_half_open_excludes_next_day_midnight():
    # Start 2026-11-03T00Z inclusive; the end calendar day (11-10) counts
    # through 23:59:59; 2026-11-11T00Z is outside.
    items = [
        _item("at_start", published_at="2026-11-03"),
        _item("end_of_day", published_at="2026-11-10 23:59"),
        _item("next_midnight", published_at="2026-11-11"),
    ]
    normalized = _normalized("news", items=items)
    assert normalized["valid_record_count"] == 2
    assert "OUT_OF_WINDOW" in normalized["reason_codes"]


@pytest.mark.unit
def test_unverifiable_items_are_dropped_with_exact_reasons():
    items = [
        _item("no_time", published_at=None),
        _item("thin", substantive=False),
        _item("later", published_at="2026-11-20"),
    ]
    normalized = _normalized("news", items=items)
    assert normalized["valid_record_count"] == 0
    assert set(normalized["reason_codes"]) == {"OUT_OF_WINDOW", "UNVERIFIABLE_METADATA"}


@pytest.mark.unit
def test_receipt_for_another_ticker_or_window_is_unavailable():
    wrong_ticker = _normalized("news", ticker="MSFT", items=[_item("x")])
    assert wrong_ticker["available"] is False
    assert "TICKER_MISMATCH" in wrong_ticker["reason_codes"]

    wrong_window = _normalized("news", start="2026-10-01", end="2026-10-08", items=[_item("x")])
    assert wrong_window["available"] is False
    assert "WINDOW_UNSUPPORTED" in wrong_window["reason_codes"]


@pytest.mark.unit
def test_plain_string_is_not_a_record():
    from tradingagents.agents.sentiment_coverage import normalize_source

    normalized = normalize_source(HEADLINE, "news", RUN, WINDOW_START, WINDOW_END)
    assert normalized["available"] is False
    assert normalized["valid_record_count"] == 0
    assert "UNVERIFIABLE_METADATA" in normalized["reason_codes"]


@pytest.mark.unit
def test_empty_and_error_placeholders_are_unavailable():
    empty = _normalized("news", text="", items=())
    assert empty["available"] is False and "EMPTY" in empty["reason_codes"]

    error = _normalized("reddit", text="<unavailable>", items=(), reasons=["FETCH_ERROR"])
    assert error["available"] is False and "FETCH_ERROR" in error["reason_codes"]


# ---------------------------------------------------------------------------
# build_sentiment_coverage: mapping keyed by source id
# ---------------------------------------------------------------------------


def _coverage(present):
    from tradingagents.agents.sentiment_coverage import build_sentiment_coverage

    outcomes = [
        _normalized(sid, items=[_item(f"{sid}-1")])
        for sid in SOURCE_IDS if sid in present
    ]
    return build_sentiment_coverage(outcomes, RUN)


@pytest.mark.unit
@pytest.mark.parametrize(
    "present,valid,status",
    [
        pytest.param(set(), 0, "NO_DATA", id="none"),
        pytest.param({"news"}, 1, "PARTIAL_DATA", id="news"),
        pytest.param({"stocktwits"}, 1, "PARTIAL_DATA", id="stocktwits"),
        pytest.param({"reddit"}, 1, "PARTIAL_DATA", id="reddit"),
        pytest.param({"news", "stocktwits"}, 2, "PARTIAL_DATA", id="news+stocktwits"),
        pytest.param({"news", "reddit"}, 2, "PARTIAL_DATA", id="news+reddit"),
        pytest.param({"stocktwits", "reddit"}, 2, "PARTIAL_DATA", id="stocktwits+reddit"),
        pytest.param({"news", "stocktwits", "reddit"}, 3, "AVAILABLE", id="all"),
    ],
)
def test_all_eight_combinations_count_and_status(present, valid, status):
    coverage = _coverage(present)
    assert isinstance(coverage["sources"], dict)
    assert list(coverage["sources"]) == list(SOURCE_IDS)   # deterministic order
    assert coverage["total_sources"] == 3
    assert coverage["valid_sources"] == valid
    assert coverage["coverage_status"] == status
    for sid in SOURCE_IDS:
        entry = coverage["sources"][sid]
        if sid in present:
            assert entry["available"] is True
        else:
            assert entry["available"] is False
            assert entry["reason_codes"] == ["NOT_COLLECTED"]


@pytest.mark.unit
def test_duplicate_reddit_does_not_exceed_one_source():
    from tradingagents.agents.sentiment_coverage import build_sentiment_coverage

    coverage = build_sentiment_coverage(
        [_normalized("reddit", items=[_item("r1")]), _normalized("reddit", items=[_item("r2")])],
        RUN,
    )
    assert coverage["valid_sources"] == 1
    assert coverage["sources"]["reddit"]["available"] is True
    assert coverage["run_id"] == RUN["run_id"] and coverage["ticker"] == TICKER


# ---------------------------------------------------------------------------
# finalize_sentiment: the model can only downgrade to UNKNOWN
# ---------------------------------------------------------------------------


def _assessment(score, band="Neutral"):
    return {"overall_band": band, "overall_score": score, "confidence": "medium", "narrative": "n"}


@pytest.mark.unit
def test_valid_neutral_is_measured():
    from tradingagents.agents.sentiment_coverage import finalize_sentiment

    result = finalize_sentiment(_coverage(SOURCE_IDS), _assessment(5.0), RUN)
    assert result["overall_band"] == "Neutral"
    assert result["overall_score"] == 5.0
    assert result["assessment_status"] == "MEASURED"


@pytest.mark.unit
@pytest.mark.parametrize("score", [0.0, 10.0])
def test_score_boundaries_are_measured(score):
    from tradingagents.agents.sentiment_coverage import finalize_sentiment

    result = finalize_sentiment(_coverage(SOURCE_IDS), _assessment(score), RUN)
    assert result["overall_score"] == score
    assert result["assessment_status"] == "MEASURED"


@pytest.mark.unit
@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), -1, 11],
                         ids=["bool", "nan", "inf", "neg", "over"])
def test_invalid_score_is_unknown(bad):
    from tradingagents.agents.sentiment_coverage import finalize_sentiment

    result = finalize_sentiment(_coverage(SOURCE_IDS), _assessment(bad), RUN)
    assert result["overall_band"] == "UNKNOWN"
    assert result["overall_score"] is None
    assert result["assessment_status"] == "UNKNOWN"


@pytest.mark.unit
def test_unknown_band_and_missing_assessment_are_unknown():
    from tradingagents.agents.sentiment_coverage import finalize_sentiment

    bad_band = finalize_sentiment(_coverage(SOURCE_IDS), _assessment(5.0, band="Vibes"), RUN)
    assert bad_band["overall_band"] == "UNKNOWN"
    none = finalize_sentiment(_coverage(SOURCE_IDS), None, RUN)
    assert none["overall_band"] == "UNKNOWN" and none["overall_score"] is None


@pytest.mark.unit
def test_zero_coverage_downgrades_injected_band():
    from tradingagents.agents.sentiment_coverage import finalize_sentiment

    result = finalize_sentiment(_coverage(set()), _assessment(5.0), RUN)
    assert result["overall_band"] == "UNKNOWN"
    assert result["overall_score"] is None
    assert result["assessment_status"] == "UNKNOWN"


@pytest.mark.unit
def test_outcome_normalized_under_other_run_cannot_count():
    # A receipt has no run_id; it binds ticker/window. Normalizing under a
    # different run must leave it unavailable for the current run.
    from tradingagents.agents.sentiment_coverage import build_sentiment_coverage

    other = dict(RUN, run_id="fr03-fixture-OTHER")
    foreign = _normalized("news", run=other, items=[_item("n1")])
    coverage = build_sentiment_coverage([foreign], RUN)
    news = coverage["sources"]["news"]
    assert news["available"] is False
    assert news["reason_codes"]  # an identity reason, never silently counted
    assert coverage["valid_sources"] == 0


@pytest.mark.unit
def test_result_serializes_strictly_without_nan():
    from tradingagents.agents.sentiment_coverage import finalize_sentiment

    result = finalize_sentiment(_coverage(SOURCE_IDS), _assessment(5.0), RUN)
    text = json.dumps(result, allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text
