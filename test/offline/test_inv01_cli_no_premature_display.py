"""INV-01 CLI test — the candidate is not shown before the gate, only after approval.

FR-01 / INV-01: the CLI must not surface the Portfolio Manager candidate as an
official recommendation while the stream is still running; only after the gate
approves may the official decision be shown, and a refused candidate shows BLOCKED
with its reason and nothing else.

These tests drive the **real** streaming entry ``cli.run.run_analysis`` with a fake
graph whose ``stream_run`` yields chunks carrying the candidate. They keep the real
``update_display`` so the live view is built for real, and snapshot the actual Rich
``Layout`` after every refresh — so assertions read the live view and message area,
not an empty stand-in console.

No network, no model, no real terminal.
"""

from __future__ import annotations

import pytest
from rich.console import Console

import cli.display as display
import cli.run as cli_run
from cli.models import AnalystType

CANDIDATE_BODY = (
    "**Rating**: Buy\n\n**Executive Summary**: buy now.\n\n**Investment Thesis**: buy."
)


def _render_layout(layout) -> str:
    """Render a Rich ``Layout`` to plain text the way the terminal would show it."""
    console = Console(record=True, width=200, height=60, force_terminal=False, color_system=None)
    console.print(layout)
    return console.export_text()


def _fake_graph(chunks):
    """A graph whose stream yields ``chunks``; ``publish`` runs the real gate.

    The run finishes normally (``complete_run``), so the gate judges a COMPLETED
    ``RunContext``; ``publish`` then calls the **real** v1 entry point
    (``evaluate_publication``) and applies its result with ``apply_publication``,
    exactly as production does. Nothing here reimplements the gate.
    """

    class _Graph:
        publish_calls = 0
        publish_status = None

        def __init__(self):
            # Where the gate re-reads each record's retained material.
            self.config = {}

        def create_run_state(self, *a, **k):
            return {"messages": []}

        def record_decision(self, *a, **k):
            pass

        def get_graph_args(self, callbacks=None):
            return {}

        def begin_checkpoint(self, *a, **k):
            return None

        def checkpoint_input(self, state):
            return state

        def clear_checkpoint_on_success(self, *a, **k):
            pass

        def end_checkpoint(self):
            pass

        def complete_run(self, final_state):
            """Mark a normally-finished run ``COMPLETED`` (C0), as production does."""
            from tradingagents.graph.trading_graph import TradingAgentsGraph

            return TradingAgentsGraph.complete_run(self, final_state)

        def publish(self, final_state):
            from tradingagents.graph.publication_gate import (
                apply_publication,
                evaluate_publication,
                publication_run,
            )

            _Graph.publish_calls += 1
            run = publication_run(final_state)
            result = evaluate_publication(
                {
                    "rating": final_state.get("candidate_rating"),
                    "argument_ids": final_state.get("candidate_argument_ids") or (),
                },
                final_state.get("argument_index") or {},
                final_state.get("evidence_index") or {},
                run,
                results_dir=self.config.get("results_dir"),
            )
            apply_publication(result, final_state)
            _Graph.publish_status = result.publication_status
            return result.publication_status

        def stream_run(self, *a, **k):
            for chunk in chunks:
                yield [], chunk

    fake = _Graph()
    fake.graph = fake
    fake.propagator = fake
    return fake


def _wire(monkeypatch, tmp_path, fake, snapshots):
    """Install the fake graph and capture the real live view after each refresh.

    Each snapshot is recorded as ``(frame_text, gate_ran)`` where ``gate_ran`` is
    whether the publication gate had executed by the time that frame was drawn.
    This lets a test separate frames drawn *before* the verdict from the final
    report drawn *after* it.
    """
    real_update = display.update_display

    def spy_update(layout, *a, **k):
        real_update(layout, *a, **k)
        snapshots.append((_render_layout(layout), fake.publish_calls > 0))

    # A non-interactive Live stand-in: ``run_analysis`` calls ``Live(layout, ...)``,
    # so it must be a *callable class*, not an instance. The layout itself is still
    # built for real by the real ``update_display`` above.
    class _NullLive:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def update(self, *a, **k):
            pass

    monkeypatch.setattr(cli_run, "TradingAgentsGraph", lambda *a, **k: fake)
    monkeypatch.setattr(cli_run, "update_display", spy_update)
    monkeypatch.setattr(cli_run, "Live", _NullLive)
    monkeypatch.setattr("cli.main.typer.prompt", lambda *a, **k: "N")
    monkeypatch.setattr(cli_run.sys, "stdin", type("S", (), {"isatty": lambda s: True})())
    monkeypatch.setattr(cli_run, "get_user_selections", lambda flags=None: {
        "ticker": "NVDA", "analysis_date": "2026-01-10",
        "analysts": [AnalystType.MARKET], "asset_type": "stock",
    })
    monkeypatch.setattr(cli_run, "_build_run_config", lambda s, c: {
        "data_cache_dir": str(tmp_path / "c"),
        "results_dir": str(tmp_path / "r"),
    })
    # The gate re-reads each record's retained material from this run's root.
    fake.config = {"results_dir": str(tmp_path / "r")}


def _approved_v1_indexes(results_dir) -> tuple[dict, dict]:
    """The run's v1 evidence and argument indexes, with material the gate can re-read.

    Evidence is **retained material**, not report prose: the file is written under
    ``{results_dir}/{ticker}/{as_of_date}/evidence/{run_id}/`` so
    ``evaluate_publication`` can read it back before approving. The argument lives
    in the authoritative ``argument_index`` and carries the run's full identity.
    """
    from pathlib import Path

    run_id = "run-a"
    evidence_id = f"ev:{run_id}:market_snapshot:call-1"
    argument_id = f"arg:bull:{run_id}:1"
    identity = {
        "contract_version": "1.0",
        "run_id": run_id,
        "ticker": "NVDA",
        "as_of_date": "2026-01-10",
    }
    root = Path(results_dir) / "NVDA" / "2026-01-10" / "evidence" / run_id
    root.mkdir(parents=True, exist_ok=True)
    (root / "call-1.md").write_text("NVDA closed at 144.90 USD on 2026-01-05.\n", encoding="utf-8")

    evidence_index = {
        "run_id": run_id,
        "evidence": {
            evidence_id: {
                **identity,
                "evidence_id": evidence_id,
                "source_kind": "market_snapshot",
                # C1 v1.0 shared record: vendor, source locator and the request
                # window are required fields, not optional context.
                "vendor": "yahoo",
                "source_ref": (
                    "tool:get_verified_market_snapshot?tool_call_id=call-1"
                    ";ticker=NVDA;effective_as_of=2026-01-10"
                    ";curr_date=2026-01-10;look_back_days=7"
                    ";window=2026-01-03..2026-01-10"
                ),
                "source": "market_snapshot",
                "excerpt": "NVDA closed at 144.90 USD.",
                "window_start": "2026-01-03",
                "window_end": "2026-01-10",
                "content_ref": f"evidence://{run_id}/call-1.md",
            },
        },
    }
    argument_index = {
        argument_id: {
            **identity,
            "argument_id": argument_id,
            "speaker": "Bull Analyst",
            # The v1 spelling of the argument body.
            "claim": "breakout text",
            "evidence_ids": [evidence_id],
        },
    }
    return evidence_index, argument_index


def _course_run() -> dict:
    """A complete C0 run context for the streamed run (COMPLETED once it finishes)."""
    return {
        "contract_version": "1.0",
        "run_id": "run-a",
        "ticker": "NVDA",
        "as_of_date": "2026-01-10",
        "execution_status": "RUNNING",
        "request_limit": 40,
    }


def _risk_chunk(*, candidate_body, candidate_rating, candidate_argument_ids,
                evidence_index=None, argument_index=None, course_run=None):
    """One stream chunk: debate histories plus the PM candidate and its internals."""
    return {
        "messages": [],
        "course_run": course_run if course_run is not None else _course_run(),
        "company_of_interest": "NVDA",
        "trade_date": "2026-01-10",
        "investment_debate_state": {
            "bull_history": "bull case", "bear_history": "bear case",
            "history": "", "current_response": "", "count": 2,
        },
        "investment_plan": "plan",
        "risk_debate_state": {
            "aggressive_history": "aggressive case",
            "conservative_history": "conservative case",
            "neutral_history": "neutral case",
            "history": "", "latest_speaker": "", "count": 3,
            "current_aggressive_response": "", "current_conservative_response": "",
            "current_neutral_response": "",
        },
        "final_trade_decision": candidate_body,
        "candidate_decision": candidate_body,
        "candidate_rating": candidate_rating,
        "candidate_argument_ids": candidate_argument_ids,
        "evidence_index": evidence_index,
        "argument_index": argument_index if argument_index is not None else {},
    }


@pytest.mark.unit
def test_blocked_candidate_is_never_shown_and_only_blocked_renders(tmp_path, monkeypatch):
    """A refused candidate never appears in the live view; BLOCKED + reason does."""
    snapshots = []
    fake = _fake_graph([
        _risk_chunk(candidate_body=CANDIDATE_BODY, candidate_rating="Buy", candidate_argument_ids=[]),
    ])
    _wire(monkeypatch, tmp_path, fake, snapshots)

    # Capture the console output of the whole run (official messages + final report).
    record = Console(record=True, width=200, force_terminal=False, color_system=None)
    monkeypatch.setattr(display, "console", record)
    monkeypatch.setattr(cli_run, "console", record)

    # flags answer the report prompts so no prompt is shown.
    cli_run.run_analysis(flags={"save": False, "show": True})

    # The gate ran exactly once and refused (empty argument ids -> no evidence).
    assert fake.publish_calls == 1
    assert fake.publish_status == "BLOCKED"

    # The candidate body never appears in any live-view snapshot nor the console output.
    assert snapshots, "expected the live view to have been rendered"
    console_text = record.export_text()
    assert "buy now" not in "\n".join(text for text, _gate_ran in snapshots)
    assert "buy now" not in console_text

    # The message area also never received the candidate body.
    message_text = "\n".join(str(c) for _ts, _t, c in display.message_buffer.messages)
    assert "buy now" not in message_text

    # The refusal is shown, with its reason, once the report is rendered.
    assert "BLOCKED" in console_text
    assert "INSUFFICIENT_EVIDENCE" in console_text


@pytest.mark.unit
def test_approved_candidate_is_shown_only_in_the_final_report(tmp_path, monkeypatch):
    """A legal candidate is held back during the stream and shown after approval.

    The approval comes from the real v1 gate reaching a run whose evidence is
    retained material it can read back, so the display-ordering assertion is
    about a genuine APPROVED verdict.
    """
    evidence_index, argument_index = _approved_v1_indexes(tmp_path / "r")

    snapshots = []
    fake = _fake_graph([
        _risk_chunk(
            candidate_body=CANDIDATE_BODY, candidate_rating="Buy",
            candidate_argument_ids=["arg:bull:run-a:1"],
            evidence_index=evidence_index, argument_index=argument_index,
        ),
    ])
    _wire(monkeypatch, tmp_path, fake, snapshots)

    record = Console(record=True, width=200, force_terminal=False, color_system=None)
    monkeypatch.setattr(display, "console", record)
    monkeypatch.setattr(cli_run, "console", record)

    cli_run.run_analysis(flags={"save": False, "show": True})

    assert fake.publish_status == "APPROVED"

    # At least one frame was drawn before the verdict; in every such frame the
    # candidate body is absent from both the live view and the message area.
    before = [text for text, gate_ran in snapshots if not gate_ran]
    assert before, "expected at least one frame drawn before the gate ran"
    assert "buy now" not in "\n".join(before)

    # Only after approval does the official decision appear in the final report.
    assert "buy now" in record.export_text()
