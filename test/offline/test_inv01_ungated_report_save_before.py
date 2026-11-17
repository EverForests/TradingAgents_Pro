"""INV-01 regression (before the R4 A-part fix) — save_reports() must not publish ungated state.

Baseline: ``712617e25a380197e38d6ee5cc4dcc7ab393cf61``. Case: T-INV01-BYPASS at the
report sink, T-FR01-SINKS (saved official report).

The gap this test targets: the CLI and ``propagate()`` call the publication gate
before writing anything, but ``TradingAgentsGraph.save_reports()`` is a public
Python entry point that writes the report tree straight from the state it is
given. A state that never passed the gate — no gate result, and the legacy
``publication_status`` absent — therefore writes a formal Markdown/HTML report
and a ``5_portfolio/decision.md`` containing an unapproved Buy (INV-01: "never
appears as an official decision").

Design (R4 A part, approved):

- The ungated case reproduces the legacy leak path: the caller hands
  ``save_reports()`` a state with an official-looking ``final_rating="Buy"`` and a
  ``final_trade_decision`` carrying a unique body marker, with no gate result and
  no old ``publication_status``. A candidate-only state would not reproduce it.
- ``save_reports()`` is called directly with ``tmp_path``. No formal Markdown, no
  HTML and no ``5_portfolio/decision.md`` may be produced. If the legacy writer
  still writes files, the failure message names them and says whether the
  Markdown and the HTML carry the rating and the body marker.
- Positive control: the same candidate taken through ``publish()`` on its own run
  is APPROVED and is still saved normally with Markdown, HTML and the decision
  file — a writer that writes nothing is not the fix.
- BLOCKED control: a state the real ``publish()`` blocked keeps producing the
  existing diagnostic report, which shows BLOCKED and carries no official rating,
  no candidate body and no decision file. Ordinary analyst sections are allowed.

``_relative_files()`` returns paths relative to ``save_path``; names and suffixes
are compared there and every read is ``(save_path / p).read_text(...)``.

R8-B migration: the ungated case now expects the approved typed refusal,
``publication_gate.PublicationRequiredError``. The starting revision wrote the
report from ``final_rating``/``final_trade_decision``; the fix is to refuse a state
that carries no ``publication_result``. Every assertion that nothing official was
written is unchanged, and any other exception still fails the case as an error, so
a configuration or file-write error can never be read as the expected refusal.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult

from tradingagents.graph import publication_gate as gate

APPROVED = "APPROVED"
BLOCKED = "BLOCKED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
COMPLETED = "COMPLETED"
CONTRACT_VERSION = "1.0"

BUY = "Buy"
TICKER = "AAPL"
AS_OF_DATE = "2026-11-10"

DECISION_FILE = Path("5_portfolio") / "decision.md"

# A unique body marker: any output containing it has released the unapproved
# candidate. Deliberately not a rating word.
CANDIDATE_MARKER = "INV01-UNPUBLISHED-CANDIDATE-BODY-7f3c"
CANDIDATE_BODY = (
    f"**Rating**: {BUY}\n\n"
    "**Executive Summary**: add on the breakout.\n\n"
    f"**Investment Thesis**: {CANDIDATE_MARKER} price holds above the upper band."
)

_MARKDOWN_SUFFIXES = (".md",)
_HTML_SUFFIXES = (".html", ".htm")
# The material file the fixture's ``content_ref`` names, and its fixed text.
MATERIAL_FILE = "call-1.md"
SNAPSHOT_MATERIAL = (
    "## Verified market data snapshot for AAPL\n\n"
    "### Recent verified closes (last 2 rows)\n\n"
    "| Date | Close |\n"
    "|---|---:|\n"
    "| 2026-11-09 | 351.60 |\n"
    "| 2026-11-10 | 348.245 |\n"
)
# The diagnostic report renderer names; a blocked run may only produce these.
_DIAGNOSTIC_MARKDOWN = Path("complete_report.md")
_DIAGNOSTIC_HTML = Path("complete_report.html")


class _UnusedModel(BaseChatModel):
    """A model that raises: these tests must not send a request."""

    @property
    def _llm_type(self) -> str:
        return "unused-fake"

    def bind_tools(self, tools, **kwargs):  # type: ignore[override]
        return self

    def _generate(self, messages, stop=None,
                  run_manager: CallbackManagerForLLMRun | None = None,
                  **kwargs) -> ChatResult:
        raise AssertionError("save_reports() must not call the model")


class _FakeClient:
    def __init__(self, llm):
        self._llm = llm

    def get_llm(self):
        return self._llm


def _make_graph(monkeypatch, tmp_path):
    """A real ``TradingAgentsGraph`` with a fake model client and isolated paths.

    ``publish()`` re-reads each record's retained material from the graph's own
    ``config["results_dir"]``, so the fixture material is written under the same
    root the graph reads (see :func:`_write_material`).
    """
    import tradingagents.graph.trading_graph as tg
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setattr(tg, "create_tier_client", lambda *a, **k: _FakeClient(_UnusedModel()))
    monkeypatch.setattr(tg, "resolve_instrument_identity", lambda t: {
        "company_name": "Apple Inc.", "sector": "Technology",
        "industry": "Consumer Electronics", "exchange": "NASDAQ", "quote_type": "EQUITY",
    })
    config = dict(DEFAULT_CONFIG)
    config.update({
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "checkpoint_enabled": False,
    })
    return tg.TradingAgentsGraph(selected_analysts=("market",), debug=False, config=config)


def _evidence_root(results_dir, run_id: str) -> Path:
    """The §4.3 retention root for ``run_id``."""
    return Path(results_dir) / TICKER / AS_OF_DATE / "evidence" / run_id


def _write_material(graph, run_id: str) -> Path:
    """Write the fixed snapshot material the fixture's ``content_ref`` names."""
    root = _evidence_root(graph.config["results_dir"], run_id)
    root.mkdir(parents=True, exist_ok=True)
    path = root / MATERIAL_FILE
    path.write_text(SNAPSHOT_MATERIAL, encoding="utf-8")
    return path


def _run_context(run_id: str) -> dict:
    """A complete C0 run context in plain, JSON-compatible form."""
    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "ticker": TICKER,
        "as_of_date": AS_OF_DATE,
        "execution_status": COMPLETED,
        "request_limit": 40,
    }


def _evidence_index_state(run_id: str) -> dict:
    """The authoritative v1 index for ``run_id`` with one accepted argument.

    Both records carry the run's full identity (the gate checks ownership on the
    record, not on an ID prefix), and the evidence record is a **retained
    market snapshot** that names material the caller writes under its live results
    root, so the reference is resolvable exactly as a collected snapshot's is. It
    is deliberately not a report record: a report names no retained material and
    cannot back a release.
    """
    evidence_id = f"ev:{run_id}:market_snapshot:call-1"
    argument_id = f"arg:bull:{run_id}:1"
    identity = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "ticker": TICKER,
        "as_of_date": AS_OF_DATE,
    }
    return {
        "run_id": run_id,
        "evidence": [{
            **identity,
            "id": evidence_id,
            "evidence_id": evidence_id,
            "source": "market_snapshot",
            "source_kind": "market_snapshot",
            "vendor": "yahoo",
            "source_ref": "tool=get_verified_market_snapshot;call_id=call-1",
            "content_ref": f"evidence://{run_id}/{MATERIAL_FILE}",
            "window_start": "2026-11-09",
            "window_end": AS_OF_DATE,
        }],
        "arguments": [{
            **identity,
            "id": argument_id,
            "argument_id": argument_id,
            "speaker": "Bull Analyst",
            "text": "trend",
            "evidence_ids": [evidence_id],
        }],
    }


def _common_state(run_id: str) -> dict:
    """What any of these run states has in common: identity and analyst sections."""
    return {
        "run_id": run_id,
        "course_run": _run_context(run_id),
        "company_of_interest": TICKER,
        "trade_date": AS_OF_DATE,
        "market_report": "AAPL closed at 348.245 USD.",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "investment_debate_state": {},
        "risk_debate_state": {},
        "investment_plan": "",
        "trader_investment_plan": "",
    }


def _ungated_leak_state(run_id: str) -> dict:
    """The legacy leak path: no gate result, no old status, official-looking fields.

    ``final_rating`` and ``final_trade_decision`` are exactly what
    ``save_reports()`` reads when nothing checked the candidate first.
    """
    return {
        **_common_state(run_id),
        "final_rating": BUY,
        "final_trade_decision": CANDIDATE_BODY,
    }


def _candidate_state(run_id: str) -> dict:
    """Ungated run state holding the Portfolio Manager's candidate for the gate to judge.

    ``evidence_index`` stays the legacy serialized shape the graph's Index Evidence
    step produces; ``argument_index`` is the authoritative ID -> record mapping the
    researchers fill (C1 v1.0), built here from the same accepted argument.
    """
    evidence_index = _evidence_index_state(run_id)
    argument = evidence_index["arguments"][0]
    argument_id = argument["argument_id"]
    return {
        **_common_state(run_id),
        "candidate_rating": BUY,
        "candidate_decision": CANDIDATE_BODY,
        "candidate_argument_ids": [argument_id],
        "evidence_index": evidence_index,
        "argument_index": {
            argument_id: {
                "contract_version": CONTRACT_VERSION,
                "run_id": run_id,
                "ticker": TICKER,
                "as_of_date": AS_OF_DATE,
                "argument_id": argument_id,
                "claim": argument["text"],
                "speaker": argument["speaker"],
                "evidence_ids": list(argument["evidence_ids"]),
            },
        },
    }


def _tree_digest(root: Path) -> str:
    """A hash of every path under ``root`` (names and contents), order-independent."""
    if not root.exists():
        return "absent"
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(str(path.relative_to(root)).encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _relative_files(root: Path) -> list[Path]:
    """Every written file as a path relative to ``root``."""
    if not root.exists():
        return []
    return sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file())


def _read(save_path: Path, files: list[Path], suffixes: tuple[str, ...]) -> str:
    """The text of the written files with these suffixes, read via ``save_path / p``."""
    return "\n".join(
        (save_path / p).read_text(encoding="utf-8", errors="replace")
        for p in files if p.suffix in suffixes
    )


def _describe_leak(save_path: Path, files: list[Path]) -> str:
    """The failure message: what was written, and what it leaked."""
    generated = ", ".join(str(p) for p in files) or "(none)"
    markdown = _read(save_path, files, _MARKDOWN_SUFFIXES)
    html = _read(save_path, files, _HTML_SUFFIXES)
    return (
        f"save_reports() wrote under {save_path}: {generated}. "
        f"Markdown contains 'Rating: {BUY}'={f'**Rating**: {BUY}' in markdown!r}, "
        f"body marker={CANDIDATE_MARKER in markdown!r}; "
        f"HTML contains 'Rating: {BUY}'={f'>Rating: {BUY}<' in html!r}, "
        f"masthead '{BUY}'={f'>{BUY}<' in html!r}, "
        f"body marker={CANDIDATE_MARKER in html!r}; "
        f"{DECISION_FILE} written={DECISION_FILE in files!r}."
    )


@pytest.mark.unit
def test_ungated_state_writes_no_official_report(monkeypatch, tmp_path):
    """Negative counterexample: state that never passed the gate must not be saved.

    The approved refusal is the typed gate error: ``save_reports()`` raises
    ``PublicationRequiredError`` and writes nothing. Every assertion that no
    official surface was produced is kept; the only change from the A-part
    revision is that the refusal itself is the expected outcome rather than an
    error, because a flat ``APPROVED``/rating is not a gate result.

    On the starting revision ``save_reports()`` writes the tree straight from
    ``final_rating``/``final_trade_decision``, so this test fails with the leak
    report.
    """
    graph = _make_graph(monkeypatch, tmp_path)
    state = _ungated_leak_state(f"course-run-ungated-{tmp_path.name}")
    assert "publication_status" not in state and "publication_result" not in state
    save_path = tmp_path / "reports"
    before = _tree_digest(save_path)

    refused = False
    try:
        graph.save_reports(state, TICKER, save_path=save_path)
    except gate.PublicationRequiredError:
        refused = True
    except Exception as exc:  # configuration/write errors are errors, not acceptance
        pytest.fail(f"save_reports() raised {type(exc).__name__}: {exc}", pytrace=False)

    files = _relative_files(save_path)
    generated = ", ".join(str(p) for p in files) or "(none)"

    if files:
        # Something was written: it may only be a nonofficial diagnostic, and no
        # formal evaluation surface may carry the candidate.
        markdown = _read(save_path, files, _MARKDOWN_SUFFIXES)
        html = _read(save_path, files, _HTML_SUFFIXES)
        assert set(files) <= {_DIAGNOSTIC_MARKDOWN, _DIAGNOSTIC_HTML}, _describe_leak(save_path, files)
        assert f"**Rating**: {BUY}" not in markdown and "Rating: Buy" not in markdown, (
            _describe_leak(save_path, files)
        )
        assert CANDIDATE_MARKER not in markdown, _describe_leak(save_path, files)
        assert f">{BUY}<" not in html and CANDIDATE_MARKER not in html, _describe_leak(save_path, files)

    assert refused, (
        "save_reports() accepted a state with no publication_result; the typed "
        "refusal (PublicationRequiredError) was not raised"
    )
    assert DECISION_FILE not in files, (
        f"an ungated run wrote the Portfolio Manager decision file: {generated}. "
        + _describe_leak(save_path, files)
    )
    assert _tree_digest(save_path) == before, (
        "an ungated run changed the report tree: " + _describe_leak(save_path, files)
    )
    assert state.get("final_rating") == BUY, (
        "save_reports() must not grant an approval: state final_rating is "
        f"{state.get('final_rating')!r}"
    )


@pytest.mark.unit
def test_approved_baseline_still_writes_markdown_and_html(monkeypatch, tmp_path):
    """Positive control: a legally gated APPROVED run writes Markdown and HTML normally."""
    graph = _make_graph(monkeypatch, tmp_path)
    run_id = f"course-run-approved-{tmp_path.name}"
    state = _candidate_state(run_id)
    # The evidence record names retained material; write it under this graph's root.
    _write_material(graph, run_id)

    status = graph.publish(state)
    assert status == APPROVED, state.get("publication_reason")
    assert state.get("final_rating") == BUY

    save_path = tmp_path / "reports"
    graph.save_reports(state, TICKER, save_path=save_path)

    files = _relative_files(save_path)
    markdown_files = [p for p in files if p.suffix in _MARKDOWN_SUFFIXES]
    html_files = [p for p in files if p.suffix in _HTML_SUFFIXES]

    assert markdown_files, f"an approved run must write Markdown; wrote {files}"
    assert html_files, f"an approved run must write HTML; wrote {files}"
    assert DECISION_FILE in files, (
        f"an approved run must write {DECISION_FILE}; wrote {files}"
    )

    markdown = _read(save_path, files, _MARKDOWN_SUFFIXES)
    html = _read(save_path, files, _HTML_SUFFIXES)
    assert f"**Rating**: {BUY}" in markdown and CANDIDATE_MARKER in markdown
    assert CANDIDATE_MARKER in html
    assert f">{BUY}<" in html, "the approved rating must appear in the HTML masthead"


@pytest.mark.unit
def test_only_the_run_identity_separates_approval_from_cross_run_refusal(monkeypatch, tmp_path):
    """A's F1 control: the same saved-run state, judged under a different run, is refused.

    This is the "identity, not content" contrast the A counterexample needs. The
    same complete v1 state — the same evidence record with its retained material,
    the same accepted argument, the same candidate — is judged twice by the real
    ``publish()``. The first judgement uses the state's own ``course_run`` and
    approves. The second changes **only** the run identity stored in
    ``course_run`` (a different ``run_id``, the same ticker and date); the
    evidence and argument records still name the original run, so they belong to
    another run and the gate refuses. A block that came from the fixture would
    have blocked the first judgement too.
    """
    graph = _make_graph(monkeypatch, tmp_path)
    run_id = f"course-run-f1-{tmp_path.name}"
    _write_material(graph, run_id)

    # Same-run positive control: the state's own identity approves and saves.
    same_run = _candidate_state(run_id)
    assert graph.publish(same_run) == APPROVED, same_run.get("publication_reason")
    assert same_run.get("final_rating") == BUY
    save_path = tmp_path / "reports"
    graph.save_reports(same_run, TICKER, save_path=save_path)
    assert DECISION_FILE in _relative_files(save_path), "the positive control wrote no decision"

    # Cross-run: identical records, only the current run identity changes.
    foreign_run = _candidate_state(run_id)
    foreign_run["course_run"] = _run_context(f"{run_id}-other")
    status = graph.publish(foreign_run)

    assert status == BLOCKED, (
        "a run citing another run's evidence must not publish, but the gate "
        f"returned {status!r}"
    )
    assert foreign_run.get("publication_reason") == INSUFFICIENT_EVIDENCE
    assert foreign_run.get("final_rating") in (None, "")
    assert CANDIDATE_MARKER not in repr(foreign_run.get("publication_result"))


@pytest.mark.unit
def test_blocked_diagnostic_report_shows_blocked_without_official_rating(monkeypatch, tmp_path):
    """A real BLOCKED run still saves the diagnostic report, free of the candidate."""
    graph = _make_graph(monkeypatch, tmp_path)
    run_id = f"course-run-blocked-{tmp_path.name}"
    state = _candidate_state(run_id)
    _write_material(graph, run_id)
    # The candidate cites nothing, so the real gate blocks it as insufficient evidence.
    state["candidate_argument_ids"] = []
    status = graph.publish(state)
    assert status == BLOCKED, f"expected the gate to block this fixture, got {status!r}"
    assert state.get("publication_reason") == INSUFFICIENT_EVIDENCE

    save_path = tmp_path / "reports"

    try:
        graph.save_reports(state, TICKER, save_path=save_path)
    except Exception as exc:  # configuration/write errors are errors, not acceptance
        pytest.fail(f"save_reports() raised {type(exc).__name__}: {exc}", pytrace=False)

    files = _relative_files(save_path)
    leak = _describe_leak(save_path, files)

    # The existing diagnostic report is generated as before.
    assert _DIAGNOSTIC_MARKDOWN in files, (
        f"a blocked run should still write {_DIAGNOSTIC_MARKDOWN}; wrote {files}"
    )
    assert _DIAGNOSTIC_HTML in files, (
        f"a blocked run should still write {_DIAGNOSTIC_HTML}; wrote {files}"
    )
    assert DECISION_FILE not in files, leak

    markdown = _read(save_path, files, _MARKDOWN_SUFFIXES)
    diagnostic_html = (save_path / _DIAGNOSTIC_HTML).read_text(encoding="utf-8", errors="replace")

    # It states the refusal, and carries no official rating or candidate body.
    assert BLOCKED in markdown, "the blocked diagnostic should state the publication status"
    assert f"**Rating**: {BUY}" not in markdown, leak
    assert "Rating: Buy" not in markdown, leak
    assert CANDIDATE_MARKER not in markdown, leak
    assert BLOCKED in diagnostic_html, "the blocked diagnostic should state the publication status"
    assert f"Rating: {BUY}<" not in diagnostic_html, leak
    assert CANDIDATE_MARKER not in diagnostic_html, leak
    # Ordinary analyst sections are allowed in the diagnostic report.
    assert "AAPL closed at 348.245 USD." in markdown
