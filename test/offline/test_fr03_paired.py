"""FR-03 paired baseline/candidate diagnostic (paired-plan-20261117-r1).

When ``FR03_BASELINE_ROOT`` names the unchanged reference checkout, this file is
executed as a worker in two separate subprocesses -- one per version, each with
its own ``sys.path`` root -- and the 16 frozen synthetic cases below are run
through the real sentiment analyst node and the real bull consumer in both.
Only an unset ``FR03_BASELINE_ROOT`` skips (the diagnostic was not requested); a
configured but invalid root fails.

Scope. Each worker replaces the three source fetchers and the LLM with fakes, so
it measures where the *coverage boundary* sits: whether an unobserved or invalid
source can still reach the model and become a measured Neutral. It does not
replay raw adapter output and says nothing about real model behaviour. The
baseline cannot express collector receipts, so its cases carry the same text as
plain strings; this is a collector-boundary comparison, and metadata a version
does not support is ignored. All counts are synthetic diagnostics, never a
natural model-error rate, cost or accuracy figure.

Nothing here contacts a network or a model: a socket guard is installed before
any project import, and every exception propagates. A subprocess import,
dependency or timeout failure is reported as such, never as a behavioural
result.
"""

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

TICKER = "AAPL"
AS_OF = "2026-11-10"
WINDOW_START = "2026-11-03"
WINDOW_END = "2026-11-10"
ITEM_AT = "2026-11-05T12:00:00Z"
SOURCES = ("news", "stocktwits", "reddit")
VENDORS = {"news": "yfinance", "stocktwits": "stocktwits", "reddit": "reddit"}
MISSING_TEXT = "<unavailable>"
FAKE_NARRATIVE = "FIXED FAKE MODEL OUTPUT: balanced fixture control."
FAKE_CONSUMER = "FIXED FAKE CONSUMER OUTPUT"
WORKER_TIMEOUT = 90
BASELINE_GIT_HEAD = "9fa1196fffbcfd9de5146d2dd2869df84ab99838"
RUN_ID = "fr03-paired-20261117"
RUN = {"contract_version": "1.0", "run_id": RUN_ID, "ticker": "AAPL",
       "as_of_date": "2026-11-10", "execution_status": "RUNNING", "request_limit": 40}
# The two headers each version renders:
#   **Overall Sentiment:** **Neutral** (Score: 5.0/10)
#   **Overall Sentiment:** **UNKNOWN**
HEADER = re.compile(
    r"^\*\*Overall Sentiment:\*\*\s*\*\*(?P<band>[A-Za-z ]+?)\*\*"
    r"(?:\s*\(Score:\s*(?P<score>\d+(?:\.\d+)?)\s*/\s*10\))?\s*$"
)

# ---------------------------------------------------------------------------
# Frozen canonical fixtures
# ---------------------------------------------------------------------------


def _body(source_id, ticker="AAPL"):
    return f"FICTIONAL TEST DATA ({source_id}): {ticker} coverage balanced, no directional claim."


NEWS_BEFORE_START = "2026-11-02T23:59:59Z"
NEWS_AT_EXCLUDED_END = "2026-11-11T00:00:00Z"
NEWS_AT_START = "2026-11-03T00:00:00Z"
NEWS_LAST_SECOND = "2026-11-10T23:59:59Z"
WORD_UNAVAILABLE = (
    "FICTIONAL TEST DATA (news): AAPL coverage balanced; data unavailable for one "
    "feed, no directional claim."
)
MSFT_ITEM = {"ticker": "MSFT", "body": _body("news", "MSFT")}

# (case id, present sources, news item override, expected available sources)
CASES = (
    ("mask_000", (), None, ()),
    ("mask_001", ("reddit",), None, ("reddit",)),
    ("mask_010", ("stocktwits",), None, ("stocktwits",)),
    ("mask_011", ("stocktwits", "reddit"), None, ("stocktwits", "reddit")),
    ("mask_100", ("news",), None, ("news",)),
    ("mask_101", ("news", "reddit"), None, ("news", "reddit")),
    ("mask_110", ("news", "stocktwits"), None, ("news", "stocktwits")),
    ("mask_111", ("news", "stocktwits", "reddit"), None, ("news", "stocktwits", "reddit")),
    ("news_before_start", ("news",), {"published_at": NEWS_BEFORE_START}, ()),
    ("news_at_excluded_end", ("news",), {"published_at": NEWS_AT_EXCLUDED_END}, ()),
    ("news_wrong_ticker", ("news",), MSFT_ITEM, ()),
    ("news_undated", ("news",), {"published_at": None}, ()),
    ("news_at_start", ("news",), {"published_at": NEWS_AT_START}, ("news",)),
    ("news_last_second", ("news",), {"published_at": NEWS_LAST_SECOND}, ("news",)),
    ("news_word_unavailable", ("news",), {"body": WORD_UNAVAILABLE}, ("news",)),
    ("invalid_news_valid_stocktwits", ("news", "stocktwits"), MSFT_ITEM, ("stocktwits",)),
)
CASE_IDS = tuple(case[0] for case in CASES)


def _case(case_id):
    for case in CASES:
        if case[0] == case_id:
            return case
    raise KeyError(case_id)


def _news_item(case_id):
    """The news item fields for one case: canonical unless overridden."""
    fields = {"item_id": f"fx-{case_id}-news", "published_at": ITEM_AT,
              "ticker": TICKER, "substantive": True, "body": _body("news")}
    fields.update(_case(case_id)[2] or {})
    return fields


def _item(case_id, source_id):
    """The metadata fields for one item: exact for every supplied source."""
    if source_id == "news":
        return {key: value for key, value in _news_item(case_id).items() if key != "body"}
    return {"item_id": f"fx-{case_id}-{source_id}", "published_at": ITEM_AT,
            "ticker": TICKER, "substantive": True}


def _texts(case_id):
    """The literal text each source returns for a case (missing -> placeholder)."""
    present = _case(case_id)[1]
    out = {}
    for source_id in SOURCES:
        if source_id not in present:
            out[source_id] = MISSING_TEXT
        elif source_id == "news":
            out[source_id] = _news_item(case_id)["body"]
        else:
            out[source_id] = _body(source_id)
    return out


def _fixture_digest():
    """SHA256 over the canonical fixture definition, in the frozen case order.

    Covers every source's exact returned text, every supplied item's metadata
    (news, StockTwits and Reddit alike) and the expected availability sets.
    """
    canonical = [
        {
            "id": case_id,
            "present": list(present),
            "texts": _texts(case_id),
            "items": {sid: _item(case_id, sid) for sid in present},
            "expected_available": list(expected),
        }
        for case_id, present, _, expected in CASES
    ]
    payload = json.dumps(
        {"version": 2, "ticker": TICKER, "as_of": AS_OF,
         "window": [WINDOW_START, WINDOW_END], "sources": list(SOURCES),
         "cases": canonical},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _is_base_version(root):
    """Whether ``root`` is the unchanged reference (no collector receipts)."""
    return not (
        (root / "tradingagents" / "dataflows" / "source_receipt.py").is_file()
        and (root / "tradingagents" / "agents" / "sentiment_coverage.py").is_file()
    )


def _sha(path):
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


# ---------------------------------------------------------------------------
# Worker internals: socket guard, fakes, one case
# ---------------------------------------------------------------------------


class _NetworkGuard:
    """Deny every outbound socket call inside a worker, counting attempts."""

    _NAMES = ("connect", "connect_ex", "sendto")

    def __init__(self):
        self.blocked = []

    def _deny(self, name):
        def deny(*args, **kwargs):
            self.blocked.append(name)
            raise RuntimeError(f"FR-03 paired worker: network access denied ({name})")

        return deny

    def __enter__(self):
        self._saved = {name: getattr(socket.socket, name) for name in self._NAMES}
        self._saved["getaddrinfo"] = socket.getaddrinfo
        for name in self._NAMES:
            setattr(socket.socket, name, self._deny(f"socket.{name}"))
        socket.getaddrinfo = self._deny("socket.getaddrinfo")
        return self

    def __exit__(self, *exc):
        for name in self._NAMES:
            setattr(socket.socket, name, self._saved[name])
        socket.getaddrinfo = self._saved["getaddrinfo"]
        return False


class _FakeModel:
    """An LLM whose "call" is a fixed report; no remote request is made.

    Membership is observed from the actual prompt content by matching each
    supplied source's exact body, so a case whose body carries an MSFT ticker or
    the word "unavailable" is still recognised when it reaches the model.
    """

    def __init__(self, case_id):
        self.calls = 0
        self.binding_calls = 0
        self.sources_seen = []
        texts = _texts(case_id)
        self._bodies = {sid: texts[sid] for sid in _case(case_id)[1]}

    def with_structured_output(self, schema, **kwargs):
        self.binding_calls += 1
        return self

    def invoke(self, prompt):
        from tradingagents.agents.schemas import SentimentBand, SentimentReport

        self.calls += 1
        parts = prompt if isinstance(prompt, list) else [prompt]
        text = "\n".join(str(getattr(part, "content", part)) for part in parts)
        # Only supplied bodies count; the missing placeholder is never evidence.
        self.sources_seen = [sid for sid in SOURCES
                             if sid in self._bodies and self._bodies[sid] in text]
        return SentimentReport(overall_band=SentimentBand.NEUTRAL, overall_score=5.0,
                               confidence="low", narrative=FAKE_NARRATIVE)


class _FakeConsumer:
    """The bull LLM: stores the prompt it was given and returns fixed text."""

    def __init__(self):
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(str(prompt))
        return SimpleNamespace(content=FAKE_CONSUMER)


def _receipt(case_id, source_id):
    """A candidate collector receipt for one supplied source."""
    from tradingagents.dataflows.source_receipt import ItemMeta

    fields = dict(_item(case_id, source_id))
    stamp = fields.pop("published_at")
    fields["published_at"] = (
        None if stamp is None else datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    )
    return ItemMeta(**fields)


def _fetcher(case_id, source_id, base):
    """A fake fetcher returning the case text, wrapped in a receipt for the candidate."""
    text = _texts(case_id)[source_id]

    def fetch(*args, **kwargs):
        if base:
            return text
        from tradingagents.dataflows.source_receipt import SourceReceipt, SourceText

        supplied = source_id in _case(case_id)[1]
        receipt = SourceReceipt(
            source_id=source_id, vendor=VENDORS[source_id], ticker=TICKER,
            window_start=WINDOW_START, window_end=WINDOW_END,
            items=(_receipt(case_id, source_id),) if supplied else (), reason_codes=(),
        )
        return SourceText(text, receipt)

    return fetch


def _parse_header(text):
    """Band/score from the header the version actually rendered, or (None, None).

    The band keeps its actual spelling (``UNKNOWN`` stays uppercase); the score
    is a float only when the header carries one.
    """
    for line in str(text).splitlines():
        match = HEADER.match(line.strip())
        if match:
            band = match.group("band").strip()
            score = match.group("score")
            return band, (float(score) if score is not None else None)
    return None, None


def _run_case(case_id, base):
    """Run the real analyst node and bull consumer for one case; observe results."""
    import tradingagents.agents.analysts.sentiment_analyst as analyst
    from tradingagents.agents.analysts.sentiment_analyst import create_sentiment_analyst
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

    calls = []

    def counting(source_id):
        fetch = _fetcher(case_id, source_id, base)

        def counted(*args, **kwargs):
            calls.append(source_id)
            return fetch(*args, **kwargs)

        return counted

    # The same state for both versions: the reference ignores the extra identity.
    state = {"company_of_interest": TICKER, "trade_date": AS_OF, "asset_type": "stock",
             "messages": [], "course_run": dict(RUN)}

    model = _FakeModel(case_id)
    with patch.object(analyst.get_news, "func", counting("news")), \
            patch.object(analyst, "fetch_stocktwits_messages", counting("stocktwits")), \
            patch.object(analyst, "fetch_reddit_posts", counting("reddit")), \
            patch.object(analyst, "jev_screen", lambda *args, **kwargs: None):
        out = create_sentiment_analyst(model)(state)

    report_text = out["sentiment_report"]
    message_text = out["messages"][0].content
    band, score = _parse_header(report_text)

    consumer = _FakeConsumer()
    create_bull_researcher(consumer)({
        "company_of_interest": TICKER, "trade_date": AS_OF, "asset_type": "stock",
        "market_report": "", "news_report": "", "fundamentals_report": "",
        "sentiment_report": report_text, "investment_debate_state": {"count": 0},
    })

    assessment = out.get("sentiment_assessment")
    record = None
    if assessment is not None:
        entries = assessment.get("sources") or {}
        record = {
            "assessment_status": assessment.get("assessment_status"),
            "overall_band": assessment.get("overall_band"),
            "overall_score": assessment.get("overall_score"),
            "confidence": assessment.get("confidence"),
            "coverage_status": assessment.get("coverage_status"),
            "valid_sources": assessment.get("valid_sources"),
            "reason_codes": list(assessment.get("assessment_reason_codes") or []),
            "available": sorted(sid for sid, e in entries.items() if (e or {}).get("available")),
            "narrative": assessment.get("narrative"),
        }
    return {
        "case": case_id,
        "source_calls": sorted(calls),
        "model_calls": model.calls,
        "binding_calls": model.binding_calls,
        "prompt_sources": model.sources_seen,
        "report_text": report_text,
        "message_text": message_text,
        "message_matches_report": message_text == report_text,
        "header_band": band,
        "header_score": score,
        "assessment": record,
        "bull_prompts": len(consumer.prompts),
        "bull_report_in_prompt": report_text in (consumer.prompts[0] if consumer.prompts else ""),
    }


def _worker(role, root, output):
    """One version: guard the network, run all cases, write aggregate JSON.

    ``role`` is the role the driver requested; the source features of the
    checkout must match it, and every mismatch or error is recorded and makes
    the worker exit non-zero while still writing its receipt.
    """
    root = Path(root).resolve()
    sys.path.insert(0, str(root))
    payload = {
        "version_role": role,
        "root": str(root),
        "git": _git_head(root),
        "python": sys.executable,
        "fixture_sha256": _fixture_digest(),
        "sha256": {},
        "cases": [],
        "errors": [],
    }
    guard = _NetworkGuard()
    try:
        if not payload["git"].get("head"):
            raise RuntimeError(f"git HEAD unreadable for {root}: {payload['git']}")
        if role == "baseline" and payload["git"]["head"] != BASELINE_GIT_HEAD:
            raise RuntimeError(
                f"baseline HEAD is {payload['git']['head']}, expected {BASELINE_GIT_HEAD}")
        features_base = _is_base_version(root)
        if (role == "baseline") != features_base:
            raise RuntimeError(
                f"{role} root does not match the requested version "
                f"(collector receipts present: {not features_base})")
        with guard:
            import tradingagents.agents.analysts.sentiment_analyst as analyst

            module_file = Path(analyst.__file__).resolve()
            payload["import_root"] = str(module_file)
            if root not in module_file.parents:
                raise RuntimeError(f"import root mismatch: {module_file}")
            payload["sha256"] = {
                "sentiment_analyst.py": _sha(module_file),
                "schemas.py": _sha(root / "tradingagents" / "agents" / "schemas.py"),
                "bull_researcher.py": _sha(
                    root / "tradingagents" / "agents" / "researchers" / "bull_researcher.py"),
            }
            payload["fixture_sha256"] = _fixture_digest()
            for case_id in CASE_IDS:
                payload["cases"].append(_run_case(case_id, role == "baseline"))
    except BaseException as exc:  # recorded, never converted into a pass
        payload["errors"].append(f"{type(exc).__name__}: {exc}")
    payload["network_blocked"] = len(guard.blocked)
    written = Path(output)
    written.parent.mkdir(parents=True, exist_ok=True)
    written.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return 1 if (payload["errors"] or guard.blocked) else 0


def _git_head(root):
    """Read-only git HEAD of the subprocess checkout; failure is recorded as null."""
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"head": None, "error": type(exc).__name__}
    return {"head": result.stdout.strip() or None, "returncode": result.returncode}


# ---------------------------------------------------------------------------
# Driver: two subprocesses, 16 parameterized cases, comparison.json
# ---------------------------------------------------------------------------


def _candidate_root():
    return Path(__file__).resolve().parents[2]


def _spawn(role, root, output, cwd):
    """Run this file as the worker for one root; never write into the baseline."""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    command = [sys.executable, "-B", str(Path(__file__).resolve()),
               "--worker", role, "--root", str(root), "--output", str(output)]
    try:
        result = subprocess.run(command, cwd=str(cwd), env=env, capture_output=True,
                                text=True, timeout=WORKER_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        pytest.fail(f"{role} worker timed out after {WORKER_TIMEOUT}s", pytrace=False)
    receipt = Path(output)
    detail = ""
    if receipt.is_file():
        try:
            recorded = json.loads(receipt.read_text(encoding="utf-8"))
            if recorded.get("errors") or recorded.get("network_blocked"):
                detail = (f"\nreceipt errors: {recorded.get('errors')}"
                          f"\nnetwork blocked: {recorded.get('network_blocked')}")
        except ValueError as exc:
            detail = f"\nreceipt unreadable: {exc}"
    if result.returncode != 0:
        pytest.fail(
            f"{role} worker exited {result.returncode} (import/dependency/error, "
            f"not a behaviour result); receipt {receipt}{detail}"
            f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            pytrace=False,
        )
    if not receipt.is_file():
        pytest.fail(f"{role} worker wrote no output", pytrace=False)
    return json.loads(receipt.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def paired(tmp_path_factory):
    """Both worker payloads, or a skip when the diagnostic was not requested.

    Only an unset ``FR03_BASELINE_ROOT`` skips: it means the diagnostic was not
    requested. An explicitly configured root that is missing or mismatched, or a
    candidate without the new code, fails instead.
    """
    baseline_env = os.environ.get("FR03_BASELINE_ROOT")
    if not baseline_env:
        pytest.skip("FR03_BASELINE_ROOT is not set; the paired FR-03 diagnostic was "
                    "not requested")
    baseline = Path(baseline_env).expanduser().resolve()
    candidate = _candidate_root().resolve()
    assert baseline != candidate, f"baseline and candidate are the same root: {baseline}"
    assert (baseline / "tradingagents").is_dir(), (
        f"FR03_BASELINE_ROOT has no tradingagents package: {baseline}")
    assert not _is_base_version(candidate), (
        f"candidate root does not carry the FR-03 collector receipts: {candidate}")

    override = os.environ.get("FR03_PAIRED_RECEIPT_DIR")
    base_dir = (Path(override).expanduser() if override
                else tmp_path_factory.mktemp("fr03_paired"))
    base_dir.mkdir(parents=True, exist_ok=True)
    # Workers run outside either checkout, so no cache or bytecode lands in one.
    payloads = {
        "baseline": _spawn("baseline", baseline, base_dir / "baseline.json",
                           cwd=candidate),
        "candidate": _spawn("candidate", candidate, base_dir / "candidate.json",
                            cwd=candidate),
    }
    for role, payload in payloads.items():
        assert payload["version_role"] == role, payload
        assert payload["errors"] == [], payload["errors"]
        assert payload["network_blocked"] == 0, payload
        assert payload["fixture_sha256"] == _fixture_digest(), role
        assert payload["git"].get("head"), payload["git"]
        assert {c["case"] for c in payload["cases"]} == set(CASE_IDS), role
    assert payloads["baseline"]["git"]["head"] == BASELINE_GIT_HEAD, payloads["baseline"]["git"]
    assert payloads["baseline"]["sha256"].get("sentiment_analyst.py")
    assert payloads["candidate"]["sha256"].get("sentiment_analyst.py")
    assert payloads["baseline"]["fixture_sha256"] == payloads["candidate"]["fixture_sha256"]

    comparison = _comparison(payloads, baseline, candidate)
    receipt_path = base_dir / "comparison.json"
    receipt_path.write_text(json.dumps(comparison, indent=2, default=str), encoding="utf-8")
    return {"payloads": payloads, "comparison": comparison, "receipt": str(receipt_path)}


def _by_case(payload):
    return {case["case"]: case for case in payload["cases"]}


def _comparison(payloads, baseline_root, candidate_root):
    """Aggregate counts plus the actual per-case receipts."""
    base, cand = _by_case(payloads["baseline"]), _by_case(payloads["candidate"])
    rows = []
    for case_id in CASE_IDS:
        expected = list(_case(case_id)[3])
        b, c = base[case_id], cand[case_id]
        record = c["assessment"] or {}
        rows.append({
            "case": case_id,
            "expected_available": expected,
            "baseline": {"header_band": b["header_band"], "header_score": b["header_score"],
                         "model_calls": b["model_calls"], "prompt_sources": b["prompt_sources"]},
            "candidate": {
                "assessment_status": record.get("assessment_status"),
                "overall_band": record.get("overall_band"),
                "overall_score": record.get("overall_score"),
                "coverage_status": record.get("coverage_status"),
                "valid_sources": record.get("valid_sources"),
                "available": record.get("available"),
                "model_calls": c["model_calls"],
                "binding_calls": c["binding_calls"],
                "prompt_sources": c["prompt_sources"],
                "header_band": c["header_band"],
                "header_score": c["header_score"],
            },
        })

    def unsupported(case_id):
        return not _case(case_id)[3]

    valid = [case_id for case_id in CASE_IDS if not unsupported(case_id)]
    zero = [case_id for case_id in CASE_IDS if unsupported(case_id)]
    return {
        "plan": "paired-plan-20261117-r1",
        "fixture_sha256": payloads["candidate"]["fixture_sha256"],
        "versions": {
            role: {"root": payload["root"], "git_head": payload["git"].get("head"),
                   "import_root": payload.get("import_root"), "python": payload["python"],
                   "sha256": payload.get("sha256"),
                   "network_blocked": payload["network_blocked"]}
            for role, payload in payloads.items()
        },
        "summary": {
            "cases": len(CASE_IDS),
            "zero_valid_cases": len(zero),
            "valid_cases": len(valid),
            "baseline_model_calls": sum(c["model_calls"] for c in base.values()),
            "candidate_model_calls": sum(c["model_calls"] for c in cand.values()),
            "baseline_unsupported_measurements": sum(
                1 for cid in zero if base[cid]["header_band"] is not None),
            "candidate_unsupported_measurements": sum(
                1 for cid in zero if (cand[cid]["assessment"] or {}).get("assessment_status")
                == "MEASURED"),
            "baseline_valid_neutral_preserved": sum(
                1 for cid in valid if base[cid]["header_band"] == "Neutral"
                and base[cid]["header_score"] == 5.0),
            "candidate_valid_neutral_preserved": sum(
                1 for cid in valid
                if (cand[cid]["assessment"] or {}).get("overall_band") == "Neutral"
                and (cand[cid]["assessment"] or {}).get("overall_score") == 5.0),
            "label": "synthetic diagnostic counts over frozen fixtures; not a natural "
                     "model-error rate, cost or accuracy measurement",
        },
        "comparison_root": str(candidate_root),
        "baseline_root": str(baseline_root),
        "cases": rows,
        "limitations": [
            "Fetchers and the LLM are fakes: this measures the coverage boundary, not "
            "vendor, adapter or model behaviour.",
            "The baseline receives the same case text as plain strings because it has no "
            "collector receipts; this is a collection-boundary test, not a replay of raw "
            "adapter output.",
            "No network, no model call and no full-graph run: no overall trading accuracy "
            "claim follows from these counts.",
            "Counts are synthetic diagnostics over 16 frozen fixtures.",
        ],
    }


def _assert_source_calls(case):
    assert case["source_calls"] == sorted(SOURCES), case["source_calls"]


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_baseline_measures_every_fixture_neutral(paired, case_id):
    """The reference calls the model once per case and renders its Neutral 5."""
    case = _by_case(paired["payloads"]["baseline"])[case_id]
    _assert_source_calls(case)
    assert case["model_calls"] == 1
    assert (case["header_band"], case["header_score"]) == ("Neutral", 5.0)
    assert case["message_matches_report"] is True
    # Every supplied body reaches the baseline call, invalid news included.
    assert case["prompt_sources"] == [
        sid for sid in SOURCES if sid in _case(case_id)[1]]
    assert case["bull_prompts"] == 1
    assert case["bull_report_in_prompt"] is True


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_candidate_measures_only_valid_sources(paired, case_id):
    """The candidate measures only when validated sources exist; the invalid ones stay out."""
    case = _by_case(paired["payloads"]["candidate"])[case_id]
    expected = list(_case(case_id)[3])
    _assert_source_calls(case)

    # The authoritative record: coverage decides, the model can only downgrade.
    record = case["assessment"]
    assert record is not None
    assert record["available"] == sorted(expected)
    assert record["valid_sources"] == len(expected)
    assert record["coverage_status"] == {0: "NO_DATA", 3: "AVAILABLE"}.get(
        len(expected), "PARTIAL_DATA")

    # The rendered report is checked against that record, never inferred from
    # the fake's intent: header, message and bull prompt must agree with it.
    if not expected:
        assert record["assessment_status"] == "UNKNOWN"
        assert record["overall_band"] == "UNKNOWN"
        assert record["overall_score"] is None
        assert (case["header_band"], case["header_score"]) == ("UNKNOWN", None)
        assert case["model_calls"] == 0
        assert case["binding_calls"] == 0
        assert case["prompt_sources"] == []
    else:
        assert record["assessment_status"] == "MEASURED"
        assert (record["overall_band"], record["overall_score"]) == ("Neutral", 5.0)
        assert (case["header_band"], case["header_score"]) == ("Neutral", 5.0)
        assert case["model_calls"] == 1
        # Only validated sources reach the prompt: an invalid news item is excluded.
        assert sorted(case["prompt_sources"]) == sorted(expected)
        assert record["narrative"] == FAKE_NARRATIVE
    assert case["message_matches_report"] is True
    assert case["bull_prompts"] == 1
    assert case["bull_report_in_prompt"] is True


def test_summary_counts_match_the_plan(paired):
    """The frozen summary counts, reported as a labelled synthetic diagnostic."""
    summary = paired["comparison"]["summary"]
    assert summary["cases"] == 16
    assert summary["zero_valid_cases"] == 5
    assert summary["valid_cases"] == 11
    assert summary["baseline_model_calls"] == 16
    assert summary["candidate_model_calls"] == 11
    assert summary["baseline_unsupported_measurements"] == 5
    assert summary["candidate_unsupported_measurements"] == 0
    assert summary["baseline_valid_neutral_preserved"] == 11
    assert summary["candidate_valid_neutral_preserved"] == 11
    versions = paired["comparison"]["versions"]
    assert versions["baseline"]["network_blocked"] == 0
    assert versions["candidate"]["network_blocked"] == 0
    assert Path(paired["receipt"]).is_file()


def main(argv=None):
    """Worker entry point: ``--worker <role> --root ROOT --output PATH``."""
    import argparse

    parser = argparse.ArgumentParser(description="FR-03 paired diagnostic worker")
    parser.add_argument("--worker", required=True, choices=("baseline", "candidate"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    return _worker(args.worker, args.root, args.output)


if __name__ == "__main__":
    sys.exit(main())
