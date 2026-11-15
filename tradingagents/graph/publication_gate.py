"""Deterministic publication gate for FR-01 / INV-01.

Owner module for the release decision described in
``architecture-blueprint.md`` (FR-01 row) and ``docs/architecture/invariants.md``
(INV-01). The gate is the single authority for whether a candidate recommendation
becomes an official decision. Model text is advisory: only evidence links the
program itself verified in *this run* can back a release, and no free-text rating
fallback is honoured around the gate.

Design (plan revision 1):
- Evidence is indexed from the run's own non-empty analyst reports *before* the
  first debate turn, so every accepted argument cites material that exists in
  this run. The index is carried on the graph state as **plain, msgpack-safe
  data** (``evidence_index`` = a dict of primitive values), never as an object,
  so checkpointed runs can be saved and resumed.
- Bull/Bear submit structured ``evidence_ids``; the program validates each against
  the run index and only then mints a run-bound ``argument_id``.
- The Portfolio Manager selects from those accepted ``argument_ids``.
- ``evaluate`` checks the whole chain (recommendation -> accepted argument ->
  this run's material) and returns one ``GateOutcome``. ``apply`` projects that
  outcome onto the run state used by the sinks (CLI, API, reports, memory).

Only two outward rejection reasons exist: ``INVALID_RATING`` and
``INSUFFICIENT_EVIDENCE``. Missing, unparseable, unknown and cross-run references
all map to ``INSUFFICIENT_EVIDENCE``; when both the rating and the evidence fail,
``INVALID_RATING`` takes precedence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tradingagents.agents.rating import RATINGS_5_TIER

# The analyst state keys whose non-empty text is admissible as run material.
_ANALYST_REPORT_KEYS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
)

# Outward rejection reasons (D1 / runtime-policy-catalog.md).
INVALID_RATING = "INVALID_RATING"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

# The five-tier scale as a set of canonical strings, for O(1) membership tests.
_RATING_SET = frozenset(RATINGS_5_TIER)

# Publication status values carried on the run state.
APPROVED = "APPROVED"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class EvidenceRecord:
    """One admissible piece of run material, addressed by a run-bound id."""

    evidence_id: str
    source: str      # analyst state key the material came from, e.g. "market_report"
    excerpt: str     # short, human-resolvable pointer into the material
    run_id: str


@dataclass(frozen=True)
class ArgumentRecord:
    """An argument accepted only because each cited evidence id resolved in this run."""

    argument_id: str
    speaker: str                  # "Bull Analyst" / "Bear Analyst"
    text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class GateOutcome:
    """The single release decision for a run."""

    status: str                              # APPROVED | BLOCKED
    reason: str | None                       # INVALID_RATING | INSUFFICIENT_EVIDENCE
    rating: str | None                       # a 5-tier rating only when APPROVED
    resolved_chain: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    # resolved_chain items: (argument_id, evidence_id, source)

    @property
    def approved(self) -> bool:
        return self.status == APPROVED


# --- the serializable on-state representation -------------------------------
#
# The graph state carries the index as plain data so a checkpoint (msgpack) can
# store it. Shape:
#   evidence_index = {
#       "run_id": str,
#       "evidence": [ {"id", "source", "excerpt"} , ... ],
#       "arguments": [ {"id", "speaker", "text", "evidence_ids"} , ... ],
#   }
# Every value is a str / list / dict of primitives.


def index_to_state(index: EvidenceIndex) -> dict:
    """Flatten an EvidenceIndex into msgpack-safe primitives for the graph state."""
    return {
        "run_id": index.run_id,
        "evidence": [
            {"id": e.evidence_id, "source": e.source, "excerpt": e.excerpt}
            for e in index.evidence_records
        ],
        "arguments": [
            {"id": a.argument_id, "speaker": a.speaker, "text": a.text,
             "evidence_ids": list(a.evidence_ids)}
            for a in index.argument_records
        ],
    }


class EvidenceIndex:
    """Run-scoped evidence and accepted arguments (in-memory helper).

    Built at run start from its own reports; ``accept`` validates submissions.
    The graph state holds ``index_to_state(...)`` rather than this object, and
    ``evaluate`` reads either shape via :func:`as_index`.
    """

    def __init__(self, run_id: str, evidence: dict[str, EvidenceRecord]):
        self.run_id = run_id
        self._evidence = dict(evidence)
        self._arguments: dict[str, ArgumentRecord] = {}

    # --- evidence ---

    def has_evidence(self, evidence_id: str) -> bool:
        return evidence_id in self._evidence

    def evidence(self, evidence_id: str) -> EvidenceRecord:
        return self._evidence[evidence_id]

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(self._evidence)

    @property
    def evidence_records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(self._evidence.values())

    # --- accepted arguments ---

    def accept(self, argument: ArgumentRecord) -> bool:
        """Accept an argument iff every cited evidence id resolves in this run.

        Returns whether it was accepted. Rejection leaves the index unchanged;
        the caller must not mint an argument id for a rejected submission.
        """
        if not argument.evidence_ids:
            return False
        if any(eid not in self._evidence for eid in argument.evidence_ids):
            return False
        self._arguments[argument.argument_id] = argument
        return True

    def argument(self, argument_id: str) -> ArgumentRecord:
        return self._arguments[argument_id]

    def has_argument(self, argument_id: str) -> bool:
        return argument_id in self._arguments

    @property
    def argument_ids(self) -> tuple[str, ...]:
        return tuple(self._arguments)

    @property
    def argument_records(self) -> tuple[ArgumentRecord, ...]:
        return tuple(self._arguments.values())


def as_index(value) -> EvidenceIndex:
    """A read-only EvidenceIndex view of either an object or the state dict.

    ``evaluate`` accepts the graph state's serializable dict or an in-memory
    index, so the same logic serves tests and resumed checkpoints.
    """
    if isinstance(value, EvidenceIndex):
        return value
    if value is None:
        return EvidenceIndex(run_id="", evidence={})
    run_id = value.get("run_id", "")
    evidence = {
        item["id"]: EvidenceRecord(
            evidence_id=item["id"], source=item["source"],
            excerpt=item.get("excerpt", ""), run_id=run_id,
        )
        for item in value.get("evidence", [])
    }
    index = EvidenceIndex(run_id=run_id, evidence=evidence)
    for arg in value.get("arguments", []):
        index._arguments[arg["id"]] = ArgumentRecord(
            argument_id=arg["id"], speaker=arg.get("speaker", ""),
            text=arg.get("text", ""), evidence_ids=tuple(arg.get("evidence_ids", [])),
        )
    return index


def build_evidence_index(run_id: str, state) -> EvidenceIndex:
    """Index this run's non-empty analyst reports, one ``evidence_id`` per report.

    Only material actually present in the run is indexed. Deterministic: ids and
    iteration order follow the fixed analyst key order, never model text.
    """
    evidence: dict[str, EvidenceRecord] = {}
    for key in _ANALYST_REPORT_KEYS:
        text = state.get(key)
        if not isinstance(text, str) or not text.strip():
            continue
        evidence_id = f"ev:{run_id}:{key}"
        evidence[evidence_id] = EvidenceRecord(
            evidence_id=evidence_id, source=key, excerpt=_excerpt(text), run_id=run_id,
        )
    return EvidenceIndex(run_id=run_id, evidence=evidence)


def evidence_menu(index) -> str:
    """The evidence IDs and their material, for the researcher prompt.

    The model may cite only these IDs; they are the program-built index for this
    run, so a cited ID resolves to actual run material.
    """
    idx = as_index(index)
    if not idx.evidence_ids:
        return "(No evidence is available in this run; you cannot cite any evidence ID.)"
    lines = []
    for record in idx.evidence_records:
        lines.append(f"- {record.evidence_id}  [{record.source}] {record.excerpt}")
    return "\n".join(lines)


def _excerpt(text: str, limit: int = 160) -> str:
    """A short, single-line pointer into the material (for traceability only)."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "\u2026"


def _normalize_rating(value) -> str | None:
    """The canonical 5-tier rating for ``value``, or ``None`` if not allowed.

    Accepts a bare tier string (from structured output) or a rating value enum.
    ``REVIEW`` and any out-of-scale string are not allowed ratings.
    """
    if value is None:
        return None
    rating = getattr(value, "value", value)
    if not isinstance(rating, str):
        return None
    return rating if rating in _RATING_SET else None


def evaluate(index, candidate_rating, candidate_argument_ids) -> GateOutcome:
    """Check the full chain and return the one release decision for this run.

    ``index`` may be the state dict or an EvidenceIndex. Order matters: an invalid
    rating is reported before a missing chain, so a candidate that fails both
    returns ``INVALID_RATING``. No free-text fallback is consulted here.
    """
    idx = as_index(index)
    rating = _normalize_rating(candidate_rating)
    if rating is None:
        return GateOutcome(status=BLOCKED, reason=INVALID_RATING, rating=None)

    cited = tuple(a for a in (candidate_argument_ids or ()) if a)
    resolved: list[tuple[str, str, str]] = []
    for argument_id in cited:
        if not idx.has_argument(argument_id):
            continue
        argument = idx.argument(argument_id)
        for evidence_id in argument.evidence_ids:
            if idx.has_evidence(evidence_id):
                resolved.append((argument_id, evidence_id, idx.evidence(evidence_id).source))
    if not resolved:
        return GateOutcome(status=BLOCKED, reason=INSUFFICIENT_EVIDENCE, rating=None)

    return GateOutcome(
        status=APPROVED, reason=None, rating=rating, resolved_chain=tuple(resolved),
    )


def apply(outcome: GateOutcome, final_state: dict) -> dict:
    """Project the gate outcome onto the run state consumed by every sink.

    On APPROVED the official rating and resolved chain are published and the
    candidate body becomes the official ``final_trade_decision``. On BLOCKED the
    returned state carries no candidate material at all — the candidate body,
    candidate rating and candidate argument ids are removed from the mapping, so
    the Python API's returned state cannot expose or re-derive the candidate. The
    only place ``REVIEW`` appears is the API's second tuple member (computed by the
    caller via ``run_rating``); ``final_rating`` is emptied here, not set to REVIEW.
    """
    status = outcome.status
    final_state["publication_status"] = status
    final_state["publication_reason"] = outcome.reason
    final_state["publication_chain"] = list(outcome.resolved_chain)

    if outcome.approved:
        body = final_state.get("candidate_decision") or final_state.get("final_trade_decision") or ""
        final_state["final_rating"] = outcome.rating
        final_state["final_trade_decision"] = body
        final_state.pop("candidate_decision", None)
        final_state.pop("candidate_rating", None)
        final_state.pop("candidate_argument_ids", None)
    else:
        # No candidate material leaks into the returned state: the body, its rating
        # and the ids it cited are all removed. ``final_rating`` is emptied rather
        # than set to REVIEW; REVIEW is the API's second tuple member only.
        final_state["final_rating"] = ""
        final_state["final_trade_decision"] = ""
        final_state.pop("candidate_decision", None)
        final_state.pop("candidate_rating", None)
        final_state.pop("candidate_argument_ids", None)
    return final_state
