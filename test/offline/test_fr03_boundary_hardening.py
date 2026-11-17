"""FR-03 coverage-boundary hardening (hardening-plan-20261117-r1).

Malformed or contradictory collector input is exercised directly against the
public ``normalize_source`` / ``build_sentiment_coverage`` / ``finalize_sentiment``
functions, plus one actual-node case where the news body is blank. Expected
values are frozen here; they are never produced by the code under test.
Synthetic fixtures only, no network and no model.
"""

import copy
import datetime
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

RUN = {
    "contract_version": "1.0",
    "run_id": "fr03-hardening-20261117",
    "ticker": "AAPL",
    "as_of_date": "2026-11-10",
    "execution_status": "RUNNING",
    "request_limit": 40,
}
WINDOW_START = "2026-11-03"
WINDOW_END = "2026-11-10"
TICKER = "AAPL"
SOURCE_IDS = ("news", "stocktwits", "reddit")
GENUINE = "AAPL balanced coverage; one feed unavailable but this observation is substantive."
OUTCOME_FIELDS = {
    "contract_version", "run_id", "ticker", "as_of_date", "source_id",
    "window_start", "window_end", "available", "valid_record_count",
    "reason_codes", "evidence_refs",
}


def _item(item_id="n1", substantive=True, ticker=TICKER):
    from tradingagents.dataflows.source_receipt import ItemMeta

    return ItemMeta(
        item_id=item_id,
        published_at=datetime.datetime(2026, 11, 5, 12, 0, tzinfo=datetime.UTC),
        ticker=ticker,
        substantive=substantive,
    )


_OMITTED = object()


def _source(source_id="news", text=GENUINE, items=_OMITTED, reasons=(), ticker=TICKER,
            window_end=WINDOW_END):
    from tradingagents.dataflows.source_receipt import SourceReceipt, SourceText

    receipt = SourceReceipt(
        source_id=source_id, vendor="fixture_vendor", ticker=ticker,
        window_start=WINDOW_START, window_end=window_end,
        # Omitted -> one valid item; an explicit value (including None) is passed as is.
        items=(_item(),) if items is _OMITTED else items, reason_codes=reasons,
    )
    return SourceText(text, receipt)


def _normalize(raw, source_id="news", run=RUN):
    from tradingagents.agents.sentiment_coverage import normalize_source

    return normalize_source(raw, source_id, run, WINDOW_START, WINDOW_END)


def _coverage(outcomes, run=RUN):
    from tradingagents.agents.sentiment_coverage import build_sentiment_coverage

    return build_sentiment_coverage(outcomes, run)


def _finalize(outcomes, assessment, run=RUN):
    from tradingagents.agents.sentiment_coverage import finalize_sentiment

    return finalize_sentiment(_coverage(outcomes, run), assessment, run)


# ---------------------------------------------------------------------------
# 1. Text that contradicts a valid item
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "EMPTY"),
        ("   \n\t ", "EMPTY"),
        ("<no news>", "EMPTY"),
        ("<fetch_error>", "FETCH_ERROR"),
        ("<unavailable>", "FETCH_ERROR"),
    ],
)
def test_contradictory_text_with_a_valid_item_is_unavailable(text, expected):
    outcome = _normalize(_source(text=text))
    assert outcome["available"] is False
    assert outcome["valid_record_count"] == 0
    assert outcome["evidence_refs"] == []
    assert expected in outcome["reason_codes"]


@pytest.mark.unit
def test_genuine_body_that_mentions_unavailable_stays_available():
    outcome = _normalize(_source(text=GENUINE))
    assert outcome["available"] is True
    assert outcome["valid_record_count"] == 1
    assert outcome["reason_codes"] == []
    assert outcome["evidence_refs"] == ["news/fixture_vendor:n1"]


# ---------------------------------------------------------------------------
# 2. Invalid item metadata
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "field_value", [("substantive", "false"), ("substantive", False),
                    ("substantive", 1), ("substantive", None), ("item_id", "   ")]
)
def test_invalid_item_metadata_is_unverifiable(field_value):
    field, value = field_value
    outcome = _normalize(_source(items=(replace(_item(), **{field: value}),)))
    assert outcome["available"] is False
    assert outcome["valid_record_count"] == 0
    assert outcome["evidence_refs"] == []
    assert outcome["reason_codes"] == ["UNVERIFIABLE_METADATA"]


@pytest.mark.unit
def test_item_with_unknown_ticker_is_allowed_when_other_fields_hold():
    outcome = _normalize(_source(items=(replace(_item(), ticker=None),)))
    assert outcome["available"] is True
    assert outcome["valid_record_count"] == 1
    assert outcome["reason_codes"] == []


# ---------------------------------------------------------------------------
# 3. Malformed receipts
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("items", [None, 17])
def test_malformed_item_container_is_unverifiable(items):
    outcome = _normalize(_source(items=items))
    assert outcome["available"] is False
    assert outcome["valid_record_count"] == 0
    assert outcome["reason_codes"] == ["UNVERIFIABLE_METADATA"]


@pytest.mark.unit
@pytest.mark.parametrize("items", [("n1",), ["not-an-item"], ({},)])
def test_non_item_metadata_entries_are_dropped(items):
    outcome = _normalize(_source(items=items))
    assert outcome["available"] is False
    assert outcome["valid_record_count"] == 0
    assert outcome["evidence_refs"] == []
    assert outcome["reason_codes"] == ["UNVERIFIABLE_METADATA"]


@pytest.mark.unit
@pytest.mark.parametrize("reasons", [None, 17, "FETCH_ERROR", ([[]],)])
def test_malformed_reason_codes_are_unverifiable(reasons):
    outcome = _normalize(_source(reasons=reasons))
    assert outcome["available"] is False
    assert outcome["valid_record_count"] == 0
    assert outcome["reason_codes"] == ["UNVERIFIABLE_METADATA"]


@pytest.mark.unit
@pytest.mark.parametrize("reasons", [("FETCH_ERROR",), ["FETCH_ERROR"], ()])
def test_ordinary_reason_containers_are_preserved(reasons):
    # Reasons describe failed items; they never erase a source's valid observation.
    outcome = _normalize(_source(reasons=reasons))
    assert outcome["available"] is True
    assert outcome["valid_record_count"] == 1
    assert outcome["reason_codes"] == list(reasons)


@pytest.mark.unit
def test_mixed_items_keep_only_the_valid_count():
    outcome = _normalize(_source(items=(_item("n1"), replace(_item("n2"), substantive=False))))
    assert outcome["available"] is True
    assert outcome["valid_record_count"] == 1
    assert "UNVERIFIABLE_METADATA" in outcome["reason_codes"]


# ---------------------------------------------------------------------------
# 4. Tampered manual outcomes
# ---------------------------------------------------------------------------


def _valid_outcome():
    outcome = _normalize(_source())
    assert outcome["available"] is True and outcome["valid_record_count"] == 1
    return outcome


@pytest.mark.unit
@pytest.mark.parametrize(
    "change",
    [
        {"valid_record_count": 2, "evidence_refs": ["news/fixture_vendor:n1"]},
        {"valid_record_count": 1, "evidence_refs": []},
        {"evidence_refs": [""]},
        {"evidence_refs": [17]},
        {"evidence_refs": ["x", "x"], "valid_record_count": 2},
        {"reason_codes": "FETCH_ERROR"},
        {"reason_codes": 7},
        {"reason_codes": [["EMPTY"]]},
        {"contract_version": "999"},
    ],
)
def test_tampered_outcome_is_rejected_without_mutating_input(change):
    outcome = _valid_outcome()
    outcome.update(change)
    snapshot = copy.deepcopy(outcome)
    coverage = _coverage([outcome])
    entry = coverage["sources"]["news"]
    assert coverage["valid_sources"] == 0
    assert coverage["coverage_status"] == "NO_DATA"
    assert entry["available"] is False
    assert entry["valid_record_count"] == 0
    assert entry["evidence_refs"] == []
    assert "UNVERIFIABLE_METADATA" in entry["reason_codes"]
    assert outcome == snapshot


@pytest.mark.unit
def test_valid_outcome_counts_and_finalizes_to_a_measured_neutral():
    from tradingagents.agents.schemas import SentimentBand, SentimentReport

    outcome = _valid_outcome()
    snapshot = copy.deepcopy(outcome)
    coverage = _coverage([outcome])
    assert coverage["valid_sources"] == 1
    assert coverage["coverage_status"] == "PARTIAL_DATA"
    assert coverage["sources"]["news"]["evidence_refs"] == ["news/fixture_vendor:n1"]
    assert outcome == snapshot

    report = SentimentReport(overall_band=SentimentBand.NEUTRAL, overall_score=5.0,
                             confidence="low", narrative="Synthetic balanced read.")
    final = _finalize([outcome], report)
    assert final["assessment_status"] == "MEASURED"
    assert (final["overall_band"], final["overall_score"]) == ("Neutral", 5.0)


# ---------------------------------------------------------------------------
# 5. Blank run identity
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(("field", "blank"), [("run_id", ""), ("run_id", "   "),
                                              ("ticker", ""), ("ticker", "   ")])
def test_blank_run_identity_matching_the_receipt_is_not_counted(field, blank):
    run = dict(RUN)
    run[field] = blank
    # The item's ticker follows the (possibly blank) run ticker, so it matches too.
    raw = _source(ticker=run["ticker"], items=(_item(ticker=run["ticker"]),))
    outcome = _normalize(raw, run=run)
    # Normalization must refuse the blank identity before any hand-built record.
    assert outcome["available"] is False
    assert outcome["valid_record_count"] == 0
    assert set(outcome["reason_codes"]) & {"IDENTITY_MISMATCH", "UNVERIFIABLE_METADATA"}

    manual = {key: outcome[key] for key in OUTCOME_FIELDS}
    # The receipt's blanks must not make the identity acceptable by matching itself.
    manual["available"] = True
    manual["valid_record_count"] = 1
    manual["evidence_refs"] = ["news/fixture_vendor:n1"]
    coverage = _coverage([manual], run=run)
    entry = coverage["sources"]["news"]
    assert coverage["valid_sources"] == 0
    assert entry["available"] is False
    assert set(entry["reason_codes"]) & {"IDENTITY_MISMATCH", "UNVERIFIABLE_METADATA"}


# ---------------------------------------------------------------------------
# 6. Actual node with a blank news body
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_actual_node_with_blank_news_body_skips_the_model():
    from tradingagents.agents.analysts.sentiment_analyst import create_sentiment_analyst
    from tradingagents.dataflows.source_receipt import SourceReceipt, SourceText

    def empty(source_id):
        return SourceText("<unavailable>", SourceReceipt(
            source_id=source_id, vendor="fixture_vendor", ticker=TICKER,
            window_start=WINDOW_START, window_end=WINDOW_END, items=(), reason_codes=()))

    state = {"company_of_interest": TICKER, "trade_date": "2026-11-10",
             "asset_type": "stock", "messages": [], "course_run": dict(RUN)}
    model = MagicMock()
    with patch("tradingagents.agents.analysts.sentiment_analyst.get_news") as news, \
            patch("tradingagents.agents.analysts.sentiment_analyst.fetch_stocktwits_messages",
                  return_value=empty("stocktwits")), \
            patch("tradingagents.agents.analysts.sentiment_analyst.fetch_reddit_posts",
                  return_value=empty("reddit")), \
            patch("tradingagents.agents.analysts.sentiment_analyst.jev_screen",
                  return_value=None):
        news.func.return_value = _source("news", text="   ")
        out = create_sentiment_analyst(model)(state)

    assert model.with_structured_output.call_count == 0
    assert model.invoke.call_count == 0
    assessment = out["sentiment_assessment"]
    assert assessment["overall_band"] == "UNKNOWN"
    assert assessment["overall_score"] is None
    assert assessment["valid_sources"] == 0
    assert assessment["assessment_status"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# N5. Non-finite / out-of-range numeric scores from the plain-mapping fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("score", [10 ** 400, -(10 ** 400)])
def test_huge_numeric_score_from_plain_mapping_is_unknown(score):
    """A huge integer is an invalid score, not an error: UNKNOWN/null, SCORE_INVALID."""
    outcome = _normalize(_source())
    coverage = _coverage([outcome])
    assert coverage["valid_sources"] == 1
    assert coverage["coverage_status"] == "PARTIAL_DATA"
    final = _finalize([outcome], {
        "overall_band": "Neutral",
        "overall_score": score,
        "confidence": "low",
        "narrative": "FIXED SYNTHETIC NARRATIVE: balanced fixture control.",
    })
    assert final["assessment_status"] == "UNKNOWN"
    assert final["overall_band"] == "UNKNOWN"
    assert final["overall_score"] is None
    assert final["confidence"] == "low"
    assert "SCORE_INVALID" in final["assessment_reason_codes"]


# ---------------------------------------------------------------------------
# Genuine positive headlines that begin with "No ... found ..."
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "No fraud found in AAPL audit; board clears management.",
    "No material change found in AAPL monthly operating update.",
])
def test_genuine_headline_beginning_with_no_found_stays_available(text):
    outcome = _normalize(_source(text=text))
    assert outcome["available"] is True
    assert outcome["valid_record_count"] == 1
    assert outcome["reason_codes"] == []
    assert outcome["evidence_refs"] == ["news/fixture_vendor:n1"]


# ---------------------------------------------------------------------------
# Raw vendor symbols are normalized to the run's canonical ticker
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(("raw", "canonical"), [("aapl", "AAPL"), ("BTCUSD", "BTC-USD")])
def test_raw_vendor_symbol_binds_to_canonical_run_ticker(raw, canonical):
    run = dict(RUN, ticker=canonical)
    raw_source = _source(ticker=raw, items=(_item(ticker=raw),))
    outcome = _normalize(raw_source, run=run)
    coverage = _coverage([outcome], run=run)
    assert coverage["valid_sources"] == 1
    assert coverage["coverage_status"] == "PARTIAL_DATA"
    assert outcome["ticker"] == canonical
    assert coverage["ticker"] == canonical


# ---------------------------------------------------------------------------
# Actual node: raw lowercase ticker binds to the canonical run identity
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_actual_node_with_raw_lowercase_ticker_measures_neutral():
    from tradingagents.agents.analysts.sentiment_analyst import create_sentiment_analyst
    from tradingagents.agents.schemas import SentimentBand, SentimentReport
    from tradingagents.dataflows.source_receipt import SourceReceipt, SourceText

    def empty(source_id):
        return SourceText("<unavailable>", SourceReceipt(
            source_id=source_id, vendor="fixture_vendor", ticker=TICKER,
            window_start=WINDOW_START, window_end=WINDOW_END, items=(), reason_codes=()))

    state = {"company_of_interest": "aapl", "trade_date": "2026-11-10",
             "asset_type": "stock", "messages": [], "course_run": dict(RUN)}
    structured = MagicMock()
    structured.invoke.return_value = SentimentReport(
        overall_band=SentimentBand.NEUTRAL, overall_score=5.0, confidence="low",
        narrative="FIXED SYNTHETIC NARRATIVE: balanced fixture control.")
    model = MagicMock()
    model.with_structured_output.return_value = structured
    with patch("tradingagents.agents.analysts.sentiment_analyst.get_news") as news, \
            patch("tradingagents.agents.analysts.sentiment_analyst.fetch_stocktwits_messages",
                  return_value=empty("stocktwits")), \
            patch("tradingagents.agents.analysts.sentiment_analyst.fetch_reddit_posts",
                  return_value=empty("reddit")), \
            patch("tradingagents.agents.analysts.sentiment_analyst.jev_screen",
                  return_value=None):
        news.func.return_value = _source(
            ticker="aapl", items=(_item(ticker="aapl"),))
        out = create_sentiment_analyst(model)(state)

    assert model.with_structured_output.call_count == 1
    assert structured.invoke.call_count == 1
    assert model.invoke.call_count == 0
    assessment = out["sentiment_assessment"]
    assert assessment["valid_sources"] == 1
    assert assessment["coverage_status"] == "PARTIAL_DATA"
    assert (assessment["assessment_status"], assessment["overall_band"],
            assessment["overall_score"]) == ("MEASURED", "Neutral", 5.0)
    assert assessment["ticker"] == TICKER
    assert out.get("course_run", state["course_run"]) == RUN
