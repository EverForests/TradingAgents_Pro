"""FR-03 controlled live semantic verification (school DeepSeek endpoint, r1).

This is an *integration* check of the FR-03 wiring against a real chat-completions
endpoint. It validates only that the deterministic coverage boundary, the
SentimentReport schema and the real model client agree on synthetic controls.
It says nothing about real-world market accuracy and is not production
acceptance; the exact "valid Neutral 5.0" measurement is already proven offline.

Design invariants enforced here:

* At most FOUR outgoing HTTP model attempts across the whole module by default,
  shared by all three cases through a module-level counter. During a partly spent
  verification budget a run may set a lower per-run cap with
  ``FR03_LIVE_ATTEMPT_LIMIT`` (one to four); a higher value is refused. The
  counter is incremented in a ``httpx`` request event hook, i.e. before
  transport, and the first attempt beyond the cap is refused there (counted as a
  rejection) so no request leaves. ``max_retries=0`` and no SDK retry is
  configured.
* Every source fetcher is monkeypatched; no news or social vendor is contacted.
  Only the model endpoint ``https://llm.cs.cityu.edu.hk/v1`` is reached.
* Credentials come from ``CITYU_API_KEY`` only. What an actual request carried
  is recorded by the event hook from the request body, allowlisted to the model
  alias, thinking configuration, output allowance and stream flag -- never
  headers, messages or the raw body. The client's declared configuration is
  recorded separately and labelled as declared. Each finished response is
  recorded by HTTP status code only. Token usage is not captured.
* Receipts are written to ``FR03_RECEIPT_DIR`` or this session's pytest
  temporary directory and contain synthetic fixtures, aggregated outcomes,
  attempt counts, observed request settings and a failure class. An unavailable
  endpoint or an unsupported response is a FAILED test, never a pass: only an
  exception-free run with the expected record passes.

Cases: zero valid sources (no model call, NO_DATA / UNKNOWN / null), one valid
source and three valid sources. The three-source case is the positive control: it
must return a MEASURED result whose band is Neutral or Mixed (the pre-declared
rubric for noncommittal synthetic facts) with a finite 0-10 score; the exact
neutral value is not assumed. The one-source case follows C3 either way: a
MEASURED Neutral or Mixed score, or, when the model's answer is unusable, an
UNKNOWN / null / low record with explicit reasons -- accepted only after a real
model request that finished with HTTP 200, never for a failed request.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

RUN_TICKER = "AAPL"
AS_OF_DATE = "2026-11-10"
WINDOW_START = "2026-11-03"
WINDOW_END = "2026-11-10"
BASE_URL = "https://llm.cs.cityu.edu.hk/v1"
MODEL_ID = "CS5351/DeepSeek-V4-Flash"
MAX_OUTPUT_TOKENS = 4096
MAX_ATTEMPTS = 4
THINKING_DISABLED = {"type": "disabled"}
ACCEPTED_BANDS = ("Neutral", "Mixed")


def _attempt_limit() -> int:
    """The attempt cap for this run: ``FR03_LIVE_ATTEMPT_LIMIT`` or the default 4.

    The default of four is the most any run may use; a run that must stay inside
    an already partly spent verification budget sets a lower value (one to four).
    Anything else is refused rather than silently widened or narrowed.
    """
    raw = os.environ.get("FR03_LIVE_ATTEMPT_LIMIT", "").strip()
    if not raw:
        return MAX_ATTEMPTS
    try:
        limit = int(raw)
    except ValueError:
        raise pytest.UsageError(
            f"FR03_LIVE_ATTEMPT_LIMIT must be an integer 1..{MAX_ATTEMPTS}, got {raw!r}"
        ) from None
    if not 1 <= limit <= MAX_ATTEMPTS:
        raise pytest.UsageError(
            f"FR03_LIVE_ATTEMPT_LIMIT must be 1..{MAX_ATTEMPTS}, got {limit}"
        )
    return limit


# Pre-declared synthetic fixtures: balanced, explicitly fictional, no direction.
NEWS_FACT = (
    "FICTIONAL TEST DATA: AAPL reporting was balanced; no change or directional "
    "claim is present."
)
STOCKTWITS_FACT = (
    "FICTIONAL TEST DATA: the discussed AAPL messages are balanced; no change or "
    "directional claim is present."
)
REDDIT_FACT = (
    "FICTIONAL TEST DATA: the discussed AAPL posts are balanced; no change or "
    "directional claim is present."
)
ITEM_DATE = datetime(2026, 11, 5, 12, tzinfo=UTC)

SOURCES = (
    ("news", "fixture_news"),
    ("stocktwits", "stocktwits"),
    ("reddit", "reddit"),
)

needs_key = pytest.mark.skipif(
    not os.environ.get("CITYU_API_KEY"),
    reason="CITYU_API_KEY is not set; the live check never runs without it",
)


# ---------------------------------------------------------------------------
# Shared attempt budget: counted before transport, the cap-th+1 attempt refused
# ---------------------------------------------------------------------------


class AttemptBudget:
    """A module-wide counter of outgoing model attempts with a hard cap.

    ``before_request`` is a truthful ``httpx`` request event hook: it runs after
    the request is built and before it is sent, so an incremented count is an
    attempt that would leave the process. The refusal raises inside the hook,
    which aborts the request before transport and is recorded as a rejection.
    The default cap is four; a run may set a lower per-run limit through
    ``FR03_LIVE_ATTEMPT_LIMIT`` but never a higher one.

    The hook also records what the request actually carried, from its own body,
    keeping only an allowlist: model alias, thinking configuration, the output
    allowance (``max_tokens`` or ``max_completion_tokens``) and the stream flag.
    Headers, messages and the raw body are never read out or stored.

    ``after_response`` records only the HTTP status code of each finished
    response, so "the model answered" can be told apart from "the request
    failed". No body, header or private field is kept.
    """

    _SETTING_KEYS = ("model", "thinking", "max_tokens", "max_completion_tokens", "stream")

    def __init__(self, limit: int = MAX_ATTEMPTS):
        self.limit = limit
        self.attempts = 0
        self.rejections = 0
        self.destinations = []
        self.requests = []
        self.responses = []

    @classmethod
    def _observed_settings(cls, request) -> dict:
        """The allowlisted settings of one outgoing request, or empty on failure."""
        try:
            body = json.loads(request.content)
        except (TypeError, ValueError, AttributeError):
            return {}
        if not isinstance(body, dict):
            return {}
        observed = {}
        for key in cls._SETTING_KEYS:
            if key in body:
                value = body[key]
                observed[key] = value if isinstance(value, (str, int, float, bool, dict)) else None
        # One output-allowance field, whichever name the client sent.
        if "max_completion_tokens" in observed and "max_tokens" not in observed:
            observed["max_tokens"] = observed["max_completion_tokens"]
        return observed

    def before_request(self, request):
        if self.attempts >= self.limit:
            self.rejections += 1
            raise RuntimeError(
                f"FR-03 live budget exhausted: refusing attempt {self.attempts + 1}"
            )
        self.attempts += 1
        target = str(request.url)
        if target not in self.destinations:
            self.destinations.append(target)
        self.requests.append({"url": target, "settings": self._observed_settings(request)})

    def after_response(self, response):
        """Record only the HTTP status of a finished response (no body or headers)."""
        try:
            status = int(response.status_code)
        except (AttributeError, TypeError, ValueError):
            status = None
        self.responses.append({"status_code": status})

    def snapshot(self) -> dict:
        return {
            "attempts": self.attempts,
            "rejections": self.rejections,
            "limit": self.limit,
            "destinations": list(self.destinations),
            "observed_request_settings": [dict(item) for item in self.requests],
            "observed_response_status": [dict(item) for item in self.responses],
        }


_BUDGET = AttemptBudget(limit=_attempt_limit())


@pytest.fixture(scope="module")
def budget():
    """The module-shared attempt budget, used by every case and the client."""
    return _BUDGET


@pytest.fixture(scope="module")
def live_client(budget):
    """An actual ``ChatOpenAI`` against the school endpoint, no retries."""
    if not os.environ.get("CITYU_API_KEY"):
        pytest.skip("CITYU_API_KEY is not set; the live check never runs without it")
    import httpx
    from langchain_openai import ChatOpenAI

    http_client = httpx.Client(
        event_hooks={
            "request": [budget.before_request],
            "response": [budget.after_response],
        },
        timeout=60.0,
        follow_redirects=False,
    )
    llm = ChatOpenAI(
        model=MODEL_ID,
        base_url=BASE_URL,
        api_key=os.environ["CITYU_API_KEY"],
        max_retries=0,
        timeout=60.0,
        streaming=True,
        max_tokens=MAX_OUTPUT_TOKENS,
        extra_body={"thinking": THINKING_DISABLED},
        http_client=http_client,
    )
    yield llm
    http_client.close()


@pytest.fixture(scope="module")
def receipts(tmp_path_factory):
    """The receipt directory: ``FR03_RECEIPT_DIR`` or this session's temp dir."""
    configured = os.environ.get("FR03_RECEIPT_DIR")
    directory = (
        Path(configured)
        if configured
        else tmp_path_factory.mktemp("fr03-school")
    )
    directory.mkdir(parents=True, exist_ok=True)
    return directory


# ---------------------------------------------------------------------------
# Synthetic sources: receipts built in-process, every fetcher monkeypatched
# ---------------------------------------------------------------------------


def _item(item_id):
    from tradingagents.dataflows.source_receipt import ItemMeta

    return ItemMeta(item_id=item_id, published_at=ITEM_DATE, ticker=RUN_TICKER)


def _source(source_id, text, vendor, items):
    from tradingagents.dataflows.source_receipt import SourceReceipt, SourceText

    receipt = SourceReceipt(
        source_id=source_id,
        vendor=vendor,
        ticker=RUN_TICKER,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        items=tuple(items),
        reason_codes=(),
    )
    return SourceText(text, receipt)


def _unavailable(source_id, vendor):
    from tradingagents.dataflows.source_receipt import SourceReceipt, SourceText

    receipt = SourceReceipt(
        source_id=source_id,
        vendor=vendor,
        ticker=RUN_TICKER,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        items=(),
        reason_codes=("EMPTY",),
    )
    return SourceText(f"<no {source_id} items for {RUN_TICKER}>", receipt)


def _fixtures():
    """The three synthetic sources, keyed by source id."""
    return {
        "news": _source(
            "news",
            f"## {RUN_TICKER} News (fixture vendor), from {WINDOW_START} to {WINDOW_END}:\n\n"
            f"### {NEWS_FACT}",
            "fixture_news",
            [_item("live-news-1")],
        ),
        "stocktwits": _source("stocktwits", STOCKTWITS_FACT, "stocktwits", [_item("live-st-1")]),
        "reddit": _source("reddit", REDDIT_FACT, "reddit", [_item("live-rd-1")]),
    }


def _patch_sources(monkeypatch, present):
    """Patch all three fetchers; ``present`` lists the source ids that answer.

    A source absent from ``present`` returns an explicit empty receipt. No
    adapter, network call or vendor request is ever involved.
    """
    from tradingagents.agents.analysts import sentiment_analyst as sentiment

    fixtures = _fixtures()

    def result_for(source_id, vendor):
        return fixtures[source_id] if source_id in present else _unavailable(source_id, vendor)

    vendors = dict(SOURCES)

    def news(ticker, start, end, *args, **kw):
        return result_for("news", vendors["news"])

    def stocktwits(ticker, *args, **kw):
        return result_for("stocktwits", vendors["stocktwits"])

    def reddit(ticker, *args, **kw):
        # The node passes the subreddits positionally: the fake must accept them
        # or the source is lost and the case under-counts its coverage.
        return result_for("reddit", vendors["reddit"])

    monkeypatch.setattr(sentiment.get_news, "func", news, raising=False)
    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", stocktwits)
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", reddit)
    return fixtures


# ---------------------------------------------------------------------------
# Declared client configuration (not what was sent) and usage note
# ---------------------------------------------------------------------------


def _capture_declared_config(llm) -> dict:
    """The client's DECLARED configuration, with no headers or credential values.

    This builds a payload locally and sends nothing. It records how the client
    was configured; what an actual request carried is recorded separately by
    ``AttemptBudget.before_request`` from the request body.

    The installed client names the output allowance ``max_completion_tokens`` and
    keeps the thinking setting in ``extra_body``, so both the payload (across
    both names, top-level or ``extra_body``) and the client attributes are read.
    """
    base_url = getattr(llm, "openai_api_base", None)
    try:
        payload = dict(llm._get_request_payload("ping") or {})
    except Exception as exc:  # noqa: BLE001 — metadata capture must not decide the test
        payload = None
        error = type(exc).__name__
    else:
        error = None

    extra_body = getattr(llm, "extra_body", None)
    extra_body = extra_body if isinstance(extra_body, dict) else {}

    def pick(key, attribute=None):
        if payload is not None:
            if payload.get(key) is not None:
                return payload[key]
            nested = payload.get("extra_body")
            if isinstance(nested, dict) and nested.get(key) is not None:
                return nested[key]
        if extra_body.get(key) is not None:
            return extra_body[key]
        return getattr(llm, attribute, None) if attribute else None

    allowance = pick("max_tokens")
    if allowance is None:
        allowance = pick("max_completion_tokens", "max_tokens")
    streamed = pick("stream", "streaming")

    return {
        "declared": True,
        "captured": payload is not None,
        "error": error,
        "model": pick("model", "model_name"),
        "max_tokens": allowance,
        "thinking": pick("thinking"),
        "stream": streamed,
        "base_url": str(base_url) if base_url else None,
    }


def _usage_note() -> str:
    """Why the receipt has no token usage."""
    return "Usage not captured by this harness"


# ---------------------------------------------------------------------------
# Driving the real node and persisting receipts
# ---------------------------------------------------------------------------


def _run_case(monkeypatch, llm, budget, present):
    """Drive the real sentiment node with synthetic sources and return results."""
    from tradingagents.agents.analysts.sentiment_analyst import create_sentiment_analyst
    from tradingagents.graph.propagation import Propagator

    fixtures = _patch_sources(monkeypatch, present)
    before = budget.snapshot()
    state = Propagator().create_initial_state(RUN_TICKER, AS_OF_DATE)
    out = create_sentiment_analyst(llm)(state)
    after = budget.snapshot()
    return {
        "fixtures": {sid: str(doc) for sid, doc in fixtures.items()},
        "before": before,
        "after": after,
        "out": out,
        "run": out.get("course_run") or state.get("course_run"),
    }


def _receipt_payload(case, result, llm, present, failure=None):
    """The public receipt: synthetic fixtures, coverage, outcome, attempts."""
    record = result["out"]["sentiment_assessment"]
    metadata = _capture_declared_config(llm)
    return {
        "case": case,
        "requested_sources": list(present),
        "run": result["run"],
        "coverage": {
            "status": record["coverage_status"],
            "valid_sources": record["valid_sources"],
            "total_sources": record["total_sources"],
            "sources": {
                sid: {
                    "available": entry["available"],
                    "valid_record_count": entry["valid_record_count"],
                    "reason_codes": entry["reason_codes"],
                    "evidence_refs": entry["evidence_refs"],
                }
                for sid, entry in record["sources"].items()
            },
        },
        "assessment": {
            "assessment_status": record["assessment_status"],
            "overall_band": record["overall_band"],
            "overall_score": record["overall_score"],
            "confidence": record["confidence"],
            "assessment_reason_codes": record["assessment_reason_codes"],
        },
        "attempts": result["after"],
        "attempt_limit": result["after"]["limit"],
        "attempts_this_case": (
            result["after"]["attempts"] - result["before"]["attempts"]
        ),
        "observed_request_settings": result["after"]["observed_request_settings"][
            len(result["before"]["observed_request_settings"]):
        ],
        "observed_response_status": result["after"]["observed_response_status"][
            len(result["before"]["observed_response_status"]):
        ],
        "declared_client_config": metadata,
        "response_usage": _usage_note(),
        "failure_class": failure,
        "synthetic_fixtures": result["fixtures"],
    }


def _case_observed_settings(result) -> list[dict]:
    """The allowlisted settings of the requests this case actually sent."""
    start = len(result["before"]["observed_request_settings"])
    return result["after"]["observed_request_settings"][start:]


def _assert_observed_settings(result):
    """Every request of a non-zero case carried the declared model contract."""
    entries = _case_observed_settings(result)
    attempted = result["after"]["attempts"] - result["before"]["attempts"]
    assert len(entries) >= 1, "a non-zero case must send at least one model request"
    assert len(entries) == attempted
    for entry in entries:
        settings = entry.get("settings") or {}
        assert settings.get("model") == MODEL_ID
        assert settings.get("thinking") == THINKING_DISABLED
        assert settings.get("max_tokens") == MAX_OUTPUT_TOKENS
        assert str(entry.get("url", "")).startswith(BASE_URL)
    return entries


def _write_receipt(directory, name, payload):
    """Persist one receipt; it must never contain the credential value."""
    text = json.dumps(payload, indent=2, default=str)
    _assert_no_secrets(text)
    path = Path(directory) / name
    path.write_text(text, encoding="utf-8")
    return path


def _persist_case(directory, name, result, llm, present):
    """Write the receipt as the case stands, so a failure leaves its evidence."""
    return _write_receipt(
        directory, name, _receipt_payload(name.removesuffix(".json"), result, llm, present)
    )


def _assert_no_secrets(text: str) -> None:
    """No credential value and no request-header material in an artifact."""
    key = os.environ.get("CITYU_API_KEY")
    assert not key or key not in text, "receipt must not contain the credential value"
    assert "Authorization" not in text, "receipt must not contain request headers"
    assert '"messages"' not in text, "receipt must not contain prompt messages"


def _record_failure(path, failure_class, error):
    """Mark the persisted receipt with the failure class and the error type."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    payload["failure_class"] = failure_class
    payload["error_type"] = type(error).__name__
    text = json.dumps(payload, indent=2, default=str)
    _assert_no_secrets(text)
    path.write_text(text, encoding="utf-8")


def _case_attempts(result):
    """Attempts and finished HTTP responses that belong to this case."""
    start_attempts = result["before"]["attempts"]
    start_responses = len(result["before"]["observed_response_status"])
    attempts = result["after"]["attempts"] - start_attempts
    responses = result["after"]["observed_response_status"][start_responses:]
    return attempts, responses


def _check_nonzero(result, budget, expected_status, expected_valid, require_measured=True):
    """Assertions shared by the one- and three-source cases.

    Coverage is program-owned and must match exactly. An assessment that was
    cited as evidence of a working model must be MEASURED with a Neutral or
    Mixed band and a finite 0-10 score (the positive control). The C3 contract
    also permits valid coverage plus an unusable model answer to finalize as
    UNKNOWN/null/low with explicit reasons; that branch is accepted only where
    the caller opts in (``require_measured=False``), and only when the model was
    actually called and every request of the case finished with HTTP 200 --
    an endpoint or binding failure is never an acceptance criterion.
    """
    used, responses = _case_attempts(result)
    limit = result["after"]["limit"]
    assert limit <= MAX_ATTEMPTS
    assert result["after"]["attempts"] <= limit
    assert used <= limit
    assert result["after"]["rejections"] == 0, "an attempt was refused by the budget"

    record = result["out"]["sentiment_assessment"]
    assert record["valid_sources"] == expected_valid
    assert record["total_sources"] == 3
    assert record["coverage_status"] == expected_status

    if require_measured:
        assert record["assessment_status"] == "MEASURED", (
            f"expected a measured assessment, got {record['assessment_status']} "
            f"({record['assessment_reason_codes']})"
        )
        assert record["overall_band"] in ACCEPTED_BANDS
        score = record["overall_score"]
        assert isinstance(score, (int, float)) and not isinstance(score, bool)
        assert float(score) == float(score) and 0.0 <= float(score) <= 10.0
        assert record["confidence"] in ("low", "medium", "high")
        assert record["assessment_reason_codes"] == []
        return record

    status = record["assessment_status"]
    assert status in ("MEASURED", "UNKNOWN"), f"unexpected assessment status {status}"
    if status == "MEASURED":
        assert record["overall_band"] in ACCEPTED_BANDS
        score = record["overall_score"]
        assert isinstance(score, (int, float)) and not isinstance(score, bool)
        assert float(score) == float(score) and 0.0 <= float(score) <= 10.0
        return record

    # UNKNOWN/null/low is acceptable only after a real model round trip.
    assert used >= 1, "UNKNOWN without any model request is not an acceptable answer"
    assert len(responses) >= 1, "no finished HTTP response was observed for this case"
    assert all(item.get("status_code") == 200 for item in responses), responses
    assert record["overall_band"] == "UNKNOWN"
    assert record["overall_score"] is None
    assert record["confidence"] == "low"
    assert record["assessment_reason_codes"], "an UNKNOWN record must state why"
    return record


@needs_key
@pytest.mark.integration
def test_zero_valid_sources_skips_model_call(monkeypatch, live_client, budget, receipts):
    name = "fr03-live-case0.json"
    try:
        result = _run_case(monkeypatch, live_client, budget, present=())
        _persist_case(receipts, name, result, live_client, ())

        assert result["after"]["attempts"] == 0
        assert result["after"]["rejections"] == 0
        assert result["after"]["observed_request_settings"] == []
        assert result["after"]["observed_response_status"] == []
        record = result["out"]["sentiment_assessment"]
        assert record["coverage_status"] == "NO_DATA"
        assert record["valid_sources"] == 0
        assert record["total_sources"] == 3
        assert record["assessment_status"] == "UNKNOWN"
        assert record["overall_band"] == "UNKNOWN"
        assert record["overall_score"] is None
        assert record["confidence"] == "low"
        assert "UNKNOWN" in result["out"]["sentiment_report"]

        declared = _capture_declared_config(live_client)
        assert declared["declared"] is True
        assert declared["model"] == MODEL_ID
    except Exception as exc:
        _record_failure(Path(receipts) / name, "CASE_FAILED", exc)
        raise


@needs_key
@pytest.mark.integration
def test_one_valid_source_measures_noncommittal_content(
    monkeypatch, live_client, budget, receipts
):
    name = "fr03-live-case1.json"
    try:
        result = _run_case(monkeypatch, live_client, budget, present=("news",))
        _persist_case(receipts, name, result, live_client, ("news",))

        # C3 allows valid coverage plus an unusable model answer to finalize as
        # UNKNOWN/null/low; the UNKNOWN branch still requires a real, finished
        # HTTP 200 model round trip. The three-source case stays the positive
        # control that always requires MEASURED.
        record = _check_nonzero(result, budget, "PARTIAL_DATA", 1, require_measured=False)
        _assert_observed_settings(result)
        if record["assessment_status"] == "UNKNOWN":
            assert record["overall_band"] == "UNKNOWN"
            assert record["overall_score"] is None
            assert record["confidence"] == "low"
            assert record["assessment_reason_codes"], "an UNKNOWN record must state why"
        else:
            assert record["overall_band"] in ACCEPTED_BANDS
            assert isinstance(record["overall_score"], (int, float))
            assert 0.0 <= float(record["overall_score"]) <= 10.0
        assert record["sources"]["news"]["available"] is True
        assert record["sources"]["stocktwits"]["available"] is False
        assert record["sources"]["reddit"]["available"] is False
        assert record["sources"]["news"]["reason_codes"] == []
        assert record["sources"]["stocktwits"]["reason_codes"]
        assert record["sources"]["reddit"]["reason_codes"]
        assert record["sources"]["news"]["valid_record_count"] == 1
    except Exception as exc:
        _record_failure(Path(receipts) / name, "CASE_FAILED", exc)
        raise


@needs_key
@pytest.mark.integration
def test_three_valid_sources_measure_noncommittal_content(
    monkeypatch, live_client, budget, receipts
):
    name = "fr03-live-case3.json"
    present = tuple(source_id for source_id, _ in SOURCES)
    try:
        result = _run_case(monkeypatch, live_client, budget, present=present)
        _persist_case(receipts, name, result, live_client, present)

        record = _check_nonzero(result, budget, "AVAILABLE", 3)
        _assert_observed_settings(result)
        for source_id in present:
            assert record["sources"][source_id]["available"] is True
            assert record["sources"][source_id]["evidence_refs"]

        declared = _capture_declared_config(live_client)
        assert declared["declared"] is True
        assert declared["model"] == MODEL_ID
        assert declared["max_tokens"] == MAX_OUTPUT_TOKENS
        assert declared["thinking"] == THINKING_DISABLED
        assert str(declared["base_url"]).rstrip("/") == BASE_URL
    except Exception as exc:
        _record_failure(Path(receipts) / name, "CASE_FAILED", exc)
        raise
