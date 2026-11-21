"""FR-01 evidence collection: the verified market snapshot collector.

Owner module for R8-B §4. It turns one successful ``get_verified_market_snapshot``
tool response into at most one v1 ``EvidenceRecord`` whose ``content_ref``
resolves to material this run actually retained on disk.

Contract points this module implements (C1 v1.0):

- An ``EvidenceRecord`` carries ``run_id``, ``ticker`` and ``as_of_date`` copied
  from the ``RunContext`` (never derived from the ID spelling), plus
  ``evidence_id``, ``source_kind``, ``vendor``, ``source_ref``, ``content_ref``,
  ``window_start`` and ``window_end``.
- Assigning an ID does not make empty, failed or unrelated content valid. A
  vendor-failure or no-data placeholder, a report-only run with no paired tool
  call, and material that cannot be read back all collect **no** record.
- ``content_ref`` is ``evidence://{run_id}/{name}`` and names a file under the
  retention root ``{results_dir}/{ticker}/{as_of_date}/evidence/{run_id}/``.
- Window W-A is read from the dates the snapshot actually renders (the
  "Recent verified closes" table), not from the model's requested look-back.

Retention is idempotent. Re-collecting the same response under the same run is
a cache hit: the existing material is re-read and the same record is returned,
so a resume does not rewrite evidence and a deleted file is never claimed back
(the read fails, so no record is minted).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from tradingagents.dataflows.symbols import safe_ticker_component

CONTRACT_VERSION = "1.0"
SNAPSHOT_TOOL = "get_verified_market_snapshot"
SNAPSHOT_SOURCE_KIND = "market_snapshot"
SNAPSHOT_VENDOR = "yahoo"

# The heading the verified snapshot renders above its close table.
_SNAPSHOT_HEADING = "### Recent verified closes"

# A markdown table rule / separator cell ("---", "---:", ":---:").
_RULE_RE = re.compile(r"^[-:\s|]+$")
_DATE_CELL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _run_field(run: dict, key: str) -> str:
    """One RunContext string field, required for a v1 record."""
    value = run.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"RunContext is missing a required {key!r} field: {run!r}")
    return value


def _paired_call(tool_call, state: dict) -> dict | None:
    """The paired call for the response being collected, or ``None``.

    ``tool_call`` is what the graph stored in ``tool_calls[*]``; the run state
    also keeps the same pair in ``tool_calls`` and agent-facing ``messages``. A
    report-only run pairs nothing, and the model may invoke other tools, so the
    call is only accepted when its name is the snapshot tool.
    """
    if isinstance(tool_call, dict) and tool_call.get("name") == SNAPSHOT_TOOL:
        return tool_call
    for call in state.get("tool_calls") or ():
        if isinstance(call, dict) and call.get("name") == SNAPSHOT_TOOL:
            return call
    for message in state.get("messages") or ():
        for call in getattr(message, "tool_calls", None) or ():
            if isinstance(call, dict) and call.get("name") == SNAPSHOT_TOOL:
                return call
    return None


def snapshot_window(text: str) -> tuple[str, str] | None:
    """The ``(first_date, last_date)`` W-A window of the rendered close table.

    Reads the "Recent verified closes" table and takes its first and last data
    row. ``None`` when there is no snapshot table, which is what a placeholder
    or any non-snapshot text looks like.
    """
    if not isinstance(text, str) or _SNAPSHOT_HEADING not in text:
        return None
    after = text.split(_SNAPSHOT_HEADING, 1)[1]
    dates: list[str] = []
    for line in after.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if cells and _DATE_CELL_RE.match(cells[0]):
                dates.append(cells[0])
            continue
        if dates:
            break
    if not dates:
        return None
    return min(dates), max(dates)


def _source_ref(call: dict, state: dict, window: tuple[str, str]) -> str:
    """Where the evidence came from: the tool call, its effective arguments, the window.

    The call is identified by its graph id; the ticker and run date are the ones
    the graph injected (the model never sends them); the model-facing arguments
    are recorded as sent. ``effective_as_of`` is the run's ``trade_date``, which
    is the date the snapshot window was clamped to.
    """
    args = call.get("args") or {}
    parts = [
        f"tool={SNAPSHOT_TOOL}",
        f"call_id={call.get('id', '')}",
        f"ticker={state.get('company_of_interest', '')}",
        f"effective_as_of={state.get('trade_date', '')}",
        f"curr_date={args.get('curr_date', '')}",
        f"look_back_days={args.get('look_back_days', '')}",
        f"window={window[0]}..{window[1]}",
    ]
    return ";".join(parts)


def _material_name(text: str) -> str:
    """A deterministic, content-addressed file name for one snapshot response."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{SNAPSHOT_SOURCE_KIND}-{digest}.md"


def retention_root(results_dir, run: dict) -> Path:
    """``{results_dir}/{ticker}/{as_of_date}/evidence/{run_id}/`` (R8-B §4.3).

    The ticker is validated with the existing path guard rather than
    re-implemented, so a crafted ticker cannot escape ``results_dir``.
    """
    ticker = safe_ticker_component(_run_field(run, "ticker"))
    as_of = safe_ticker_component(_run_field(run, "as_of_date"), max_len=10)
    run_id = safe_ticker_component(_run_field(run, "run_id"), max_len=64)
    return Path(results_dir) / ticker / as_of / "evidence" / run_id


def _retain(text: str, results_dir, run: dict) -> Path | None:
    """Write the snapshot material once and return its path, or ``None`` on failure."""
    try:
        root = retention_root(results_dir, run)
        path = root / _material_name(text)
        if not path.exists():
            root.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return path
    except (OSError, ValueError):
        # No retained material means no evidence: the caller mints no record
        # rather than one whose content_ref cannot resolve.
        return None


def record_market_snapshot(tool_call, tool_response, state, run, results_dir):
    """Collect one verified-snapshot response into at most one EvidenceRecord.

    Returns ``{"records": [...], "record": {...} | None}``. The records list is
    empty for anything that is not substantive this-run market evidence.
    """
    call = _paired_call(tool_call, state)
    if call is None:
        return {"records": [], "record": None}

    window = snapshot_window(tool_response)
    if window is None:
        return {"records": [], "record": None}

    path = _retain(tool_response, results_dir, run)
    if path is None:
        return {"records": [], "record": None}

    run_id = _run_field(run, "run_id")
    record = {
        "contract_version": str(run.get("contract_version") or CONTRACT_VERSION),
        "run_id": run_id,
        "ticker": _run_field(run, "ticker"),
        "as_of_date": _run_field(run, "as_of_date"),
        "evidence_id": f"ev:{run_id}:{SNAPSHOT_SOURCE_KIND}:{call.get('id', '')}",
        "source_kind": SNAPSHOT_SOURCE_KIND,
        # The analyst state key / source label the existing index readers use.
        "source": SNAPSHOT_SOURCE_KIND,
        "vendor": SNAPSHOT_VENDOR,
        "source_ref": _source_ref(call, state, window),
        "content_ref": f"evidence://{run_id}/{path.name}",
        "window_start": window[0],
        "window_end": window[1],
    }
    return {"records": [record], "record": record}


def resolve_content_ref(content_ref: str, results_dir, run: dict) -> str | None:
    """The retained material a ``content_ref`` names, or ``None`` if it is not this run's.

    The content is re-read from disk every time: a reference whose material was
    removed does not resolve, so it cannot be counted as evidence.
    """
    prefix = f"evidence://{run.get('run_id', '')}/"
    if not isinstance(content_ref, str) or not content_ref.startswith(prefix):
        return None
    name = content_ref[len(prefix):]
    if not name or "/" in name or name in {".", ".."}:
        return None
    try:
        path = retention_root(results_dir, run) / name
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
