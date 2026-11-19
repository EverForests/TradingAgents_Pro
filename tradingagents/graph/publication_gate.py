"""Deterministic publication gate for FR-01 / INV-01.

Owner module for the release decision described in
``architecture-blueprint.md`` (FR-01 row) and ``docs/architecture/invariants.md``
(INV-01). The gate is the single authority for whether a candidate recommendation
becomes an official decision. Model text is advisory: only evidence links the
program itself verified in *this run* can back a release, and no free-text rating
fallback is honoured around the gate.

Design (plan revision 1, superseded by the R8-B C1 v1.0 section below):
- The run's evidence index is built *before* the first debate turn from material
  the run actually retained (the market analyst's verified snapshots), so every
  accepted argument cites material that exists in this run. An analyst report is
  **not** evidence: prose alone has no traceable retained source. The index is
  carried on the graph state as **plain, msgpack-safe data** (``evidence_index`` =
  an ``evidence_id`` -> record mapping), never as an object, so checkpointed runs
  can be saved and resumed.
- Bull/Bear submit structured ``evidence_ids``; the program validates each against
  the run index and only then mints a run-bound ``argument_id``.
- The Portfolio Manager selects from those accepted ``argument_ids``.
- ``evaluate_publication`` checks the whole chain (recommendation -> accepted
  argument -> this run's retained material) and returns one ``PublicationResult``.
  ``apply_publication`` projects that result onto the run state used by the sinks
  (CLI, API, reports, memory).

Only two outward rejection reasons exist: ``INVALID_RATING`` and
``INSUFFICIENT_EVIDENCE``. Missing, unparseable, unknown and cross-run references
all map to ``INSUFFICIENT_EVIDENCE``; when both the rating and the evidence fail,
``INVALID_RATING`` takes precedence.

C1 v1.0 (``evaluate_publication`` / ``PublicationResult``):
- The authoritative indexes are ID -> record **mappings**: ``argument_index``
  keyed by ``argument_id``, ``evidence_index`` keyed by ``evidence_id``. The old
  ``index_to_state`` lists and ``accepted_arguments`` stay as a compatibility
  layer and are never a release authority.
- Rows are applied in order: C0 terminal/incomplete execution, then an invalid
  rating, then insufficient references; APPROVED is the only state with a rating.
- Every record is identity-checked against the ``RunContext`` (a foreign run's
  material never resolves) and every reference is rechecked from the candidate,
  never trusted from the model.
- ``PublicationResult`` is the one result all four sinks (CLI, Python return,
  saved report, decision memory) consume; ``PublicationRequiredError`` refuses an
  official write when a state carries no real result.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from tradingagents.agents.rating import RATINGS_5_TIER

logger = logging.getLogger(__name__)

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

# C0 execution states. Only COMPLETED may publish; each terminal failure keeps its
# own reason code, and any other non-completed state is RUN_NOT_COMPLETE.
EXECUTION_COMPLETED = "COMPLETED"
EXECUTION_FAILED = "FAILED"
BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
CONTEXT_TOO_LARGE = "CONTEXT_TOO_LARGE"
RUN_NOT_COMPLETE = "RUN_NOT_COMPLETE"
# Terminal failures that keep their own code. FAILED is terminal too, but its
# outward reason is RUN_NOT_COMPLETE (see ``evaluate_publication``).
_TERMINAL_EXECUTION = (BUDGET_EXHAUSTED, CONTEXT_TOO_LARGE, EXECUTION_FAILED)
# Terminal states whose reason code is its own name.
_TERMINAL_EXECUTION_NAMED = (BUDGET_EXHAUSTED, CONTEXT_TOO_LARGE)


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


@dataclass(frozen=True)
class PublicationResult:
    """The one authoritative C1 v1.0 publication result, shared by all four sinks.

    Identity is copied from the ``RunContext``; it is never inferred from the
    spelling of an ID. ``rating`` is a 5-tier rating only on APPROVED and is
    ``None`` on BLOCKED, so a refused candidate's rating can never be read from
    this record. The candidate's prose is deliberately not a field here: the
    result carries the verdict and the validated references, never the body.
    """

    contract_version: str          # "1.0"
    run_id: str
    ticker: str
    as_of_date: str
    publication_status: str        # APPROVED | BLOCKED
    reason_codes: tuple[str, ...]  # rejection reasons, empty on APPROVED
    rating: str | None             # a 5-tier rating only when APPROVED, else None
    argument_ids: tuple[str, ...]  # accepted argument ids that resolved, in order
    evidence_ids: tuple[str, ...]  # this run's evidence ids they resolved through
    resolved_chain: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    # resolved_chain items: (argument_id, evidence_id, source)

    @property
    def approved(self) -> bool:
        return self.publication_status == APPROVED

    @property
    def reason(self) -> str | None:
        """The first rejection reason, for the legacy single-reason state fields."""
        return self.reason_codes[0] if self.reason_codes else None

    def as_state(self) -> dict:
        """Plain, msgpack-safe primitives for the graph state (``publication_result``)."""
        return {
            "contract_version": self.contract_version,
            "run_id": self.run_id,
            "ticker": self.ticker,
            "as_of_date": self.as_of_date,
            "publication_status": self.publication_status,
            "reason_codes": list(self.reason_codes),
            "rating": self.rating,
            "argument_ids": list(self.argument_ids),
            "evidence_ids": list(self.evidence_ids),
            "resolved_chain": [list(link) for link in self.resolved_chain],
        }


class PublicationRequiredError(RuntimeError):
    """An official surface was asked to publish without a real gate result.

    Raised instead of writing an official report or decision when the run state
    carries no ``publication_result``, or carries only the legacy flat
    ``publication_status`` field. The flat field is not a release authority: a
    caller could set it to ``APPROVED`` without any gate ever running.
    """




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
    """A read-only EvidenceIndex view of an object, the legacy state dict, or a mapping.

    ``evaluate``/``evidence_menu`` accept the graph state's serializable dict or
    an in-memory index, so the same logic serves tests and resumed checkpoints.
    A legacy serialized index stores its rows in lists; the C1 v1.0 shape stores
    them in ID-keyed mappings. Both are read here, so a snapshot record collected
    as a mapping is visible to the researchers exactly like a report record.
    """
    if isinstance(value, EvidenceIndex):
        return value
    if value is None:
        return EvidenceIndex(run_id="", evidence={})
    run_id = value.get("run_id", "")

    if isinstance(value.get("evidence"), list):
        rows = value["evidence"]
    elif isinstance(value.get("evidence"), dict):
        rows = list(value["evidence"].values())
    else:
        # A bare ID -> record mapping: everything that is not metadata is a row.
        rows = [
            record for key, record in value.items()
            if isinstance(record, dict) and (record.get("evidence_id") or record.get("id"))
        ]
    evidence = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        evidence_id = item.get("evidence_id") or item.get("id")
        if not evidence_id:
            continue
        evidence[evidence_id] = EvidenceRecord(
            evidence_id=evidence_id,
            source=item.get("source") or item.get("source_kind", ""),
            excerpt=item.get("excerpt") or _excerpt(item.get("source_ref", "")),
            run_id=item.get("run_id") or run_id,
        )

    index = EvidenceIndex(run_id=run_id, evidence=evidence)
    if isinstance(value.get("arguments"), list):
        argument_rows = value["arguments"]
    else:
        argument_rows = [
            record for key, record in value.items()
            if isinstance(record, dict) and (record.get("argument_id") or record.get("id"))
        ]
    for arg in argument_rows:
        if not isinstance(arg, dict):
            continue
        argument_id = arg.get("argument_id") or arg.get("id")
        if not argument_id:
            continue
        index._arguments[argument_id] = ArgumentRecord(
            argument_id=argument_id, speaker=arg.get("speaker", ""),
            text=arg.get("text") or arg.get("claim", ""),
            evidence_ids=tuple(arg.get("evidence_ids", [])),
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


def evidence_menu(index, aliases: dict[str, str] | None = None) -> str:
    """The evidence IDs and their material, for the researcher prompt.

    The model may cite only these IDs; they are the program-built index for this
    run, so a cited ID resolves to actual run material.
    """
    idx = as_index(index)
    if not idx.evidence_ids:
        return "(No evidence is available in this run; you cannot cite any evidence ID.)"
    selections = {reference: alias for alias, reference in (aliases or {}).items()}
    lines = []
    for record in idx.evidence_records:
        suffix = f" = {selections[record.evidence_id]}" if record.evidence_id in selections else ""
        lines.append(f"- {record.evidence_id}  [{record.source}] {record.excerpt}{suffix}")
    return "\n".join(lines)


def _excerpt(text: str, limit: int = 160) -> str:
    """A short, single-line pointer into the material (for traceability only)."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "\u2026"


# FR-01 / ADR-001: aliases are local model selections. C1 receives canonical IDs.
def _select_aliases(references, prefix: str) -> dict[str, str]:
    """Build an invocation-local menu without shadowing opaque canonical IDs."""
    canonical = tuple(dict.fromkeys(
        reference for reference in references if isinstance(reference, str) and reference
    ))
    reserved = set(canonical)
    aliases = {}
    number = 1
    for reference in canonical:
        while f"{prefix}{number}" in reserved:
            number += 1
        aliases[f"{prefix}{number}"] = reference
        number += 1
    return aliases


def _resolve_selections(selections, aliases: dict[str, str], actor: str) -> list[str]:
    """Resolve exact selections, preserving invalid references for C1 rejection."""
    canonical = set(aliases.values())
    resolved = []
    for selection in selections or ():
        if isinstance(selection, str) and selection in aliases:
            resolved.append(aliases[selection])
        else:
            if selection not in canonical:
                logger.warning(
                    "Reference rejected: actor=%s reference=%r reason=UNKNOWN_REFERENCE",
                    actor, repr(selection)[:160],
                )
            resolved.append(selection)
    return resolved


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


# --- C1 v1.0: mapping-authoritative evaluation -------------------------------
#
# The authoritative indexes are ID -> record mappings: ``argument_index`` keyed by
# ``argument_id`` and ``evidence_index`` keyed by ``evidence_id``. The legacy
# shapes ``index_to_state(...)`` (lists under "evidence"/"arguments") and
# ``accepted_arguments`` are a compatibility layer only: an argument that exists
# solely in that view never resolves a reference.


_IDENTITY_KEYS = ("run_id", "ticker", "as_of_date")

# C1 v1.0 required shared fields, beyond identity. "A missing required field is an
# invalid record": a record without one is not admissible evidence/acceptance.
_EVIDENCE_REQUIRED = (
    "evidence_id", "source_kind", "vendor", "source_ref",
    "content_ref", "window_start", "window_end",
)
_ARGUMENT_REQUIRED = ("argument_id", "claim")


def _field_present(record: dict, key: str) -> bool:
    """Whether a required field is present and non-empty.

    A missing value, ``None``, an empty string and a whitespace-only string are
    all the same thing here: no value. A list is present when it is non-empty.
    """
    value = record.get(key)
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return len(value) > 0
    return value is not None


def _required_fields_ok(record, required) -> bool:
    """Whether every C1 required field of ``record`` is present and non-empty."""
    if not isinstance(record, dict):
        return False
    return all(_field_present(record, key) for key in required)


def _identity(record, run: dict) -> tuple[str, str, str] | None:
    """The record's ``(run_id, ticker, as_of_date)`` when it *fully* matches the run.

    Ownership is checked on the record's full identity, never on how its ID is
    spelled: an ID needs no prefix and must not contain the run id. All three
    fields are required and must equal the ``RunContext``'s, so a record with a
    missing identity, a partial identity or a foreign run's identity is not this
    run's material and never resolves.
    """
    if not isinstance(record, dict):
        return None
    if not all(isinstance(run.get(key), str) and run.get(key) for key in _IDENTITY_KEYS):
        return None
    for key in _IDENTITY_KEYS:
        if record.get(key) != run.get(key):
            return None
    return tuple(run[key] for key in _IDENTITY_KEYS)


def _material_resolves(record: dict, run: dict, results_dir) -> bool:
    """Whether the record's referenced retained material exists **and has content**.

    Only a record that names retained material (``content_ref``) and whose material
    can be re-read from this run's retention root counts. A record with no
    ``content_ref`` — an analyst report indexed only in memory — has no traceable
    source material, so it is **not** admissible evidence: the prose itself is not
    a retained source. A reference whose file is expired, deleted or foreign does
    not resolve either.

    C1 v1.0: "assigning an ID does not make empty, failed or unrelated content
    valid". A retained file that resolves but holds only whitespace has no
    substance, so it is not evidence.
    """
    content_ref = record.get("content_ref")
    if not isinstance(content_ref, str) or not content_ref:
        return False
    if not isinstance(results_dir, (str, Path)) or not str(results_dir):
        return False
    from tradingagents.agents.evidence_collection import resolve_content_ref

    try:
        material = resolve_content_ref(content_ref, results_dir, run)
    except (OSError, ValueError):
        return False
    if not isinstance(material, str):
        return False
    # A retained file that exists but holds only whitespace has no substance.
    return bool(material.strip())


def _evidence_records(evidence_index, run: dict, results_dir=None) -> dict[str, dict]:
    """The run's own evidence, keyed by ``evidence_id``.

    Only the authoritative v1 mapping (or the legacy serialized list, which
    carries the same records) is read; an in-memory ``EvidenceIndex`` object is
    the compatibility layer and is refused here, because an object carries no
    per-record ``content_ref`` and would therefore skip the material read-back.

    A record counts only when its **full identity** matches the ``RunContext``;
    the ID's spelling is irrelevant. A record whose referenced retained material
    cannot be resolved is not evidence, so a report record with no ``content_ref``
    never backs a release.
    """
    if not isinstance(evidence_index, dict):
        return {}
    rows = _mapping_rows(evidence_index, "evidence", "id")
    records: dict[str, dict] = {}
    for _key, record in rows:
        if not isinstance(record, dict):
            continue
        # C1: "a missing required field is an invalid record". The *record* is
        # judged, never its mapping key or a legacy ``id`` alias: an index entry
        # that supplies ``evidence_id`` only by being keyed under it still has no
        # ``evidence_id`` of its own, so it is not evidence.
        if not _required_fields_ok(record, _EVIDENCE_REQUIRED):
            continue
        evidence_id = record["evidence_id"]
        if not isinstance(evidence_id, str) or not evidence_id:
            continue
        # Ownership is the record's full identity, never the ID's spelling.
        if _identity(record, run) is None:
            continue
        if not _material_resolves(record, run, results_dir):
            continue
        records[evidence_id] = record
    return records


def _argument_records(argument_index, run: dict) -> dict[str, dict]:
    """The run's accepted arguments, keyed by ``argument_id``.

    Only the authoritative v1 mapping (or the legacy serialized list, which
    carries the same records) is read; an ``EvidenceIndex`` object or a
    ``{"accepted_arguments": [...]}`` view is the compatibility layer and is not
    a release authority, so it yields nothing here.

    A record counts only when its **full identity** matches the ``RunContext``
    (``run_id``, ``ticker`` and ``as_of_date`` all equal). An ID needs no prefix
    and must not contain the run id. A record that states no identity at all is
    not owned by any run and is refused, whether or not a run id is available.
    """
    if not isinstance(argument_index, dict):
        return {}
    if "accepted_arguments" in argument_index and "arguments" not in argument_index:
        return {}
    rows = _mapping_rows(argument_index, "arguments", "id")
    records: dict[str, dict] = {}
    for key, record in rows:
        if not isinstance(record, dict):
            continue
        argument_id = record.get("argument_id") or record.get("id") or key
        if not isinstance(argument_id, str) or not argument_id:
            continue
        if _identity(record, run) is None:
            # No identity, a partial identity, or another run's identity.
            continue
        # C1: an AcceptedArgument needs a nonempty claim and a nonempty
        # ``evidence_ids`` list. ``text`` is the legacy spelling of the claim.
        normalised = {
            **record,
            "argument_id": argument_id,
            "claim": record.get("claim") or record.get("text") or "",
        }
        if not _required_fields_ok(normalised, _ARGUMENT_REQUIRED):
            continue
        if not _field_present(normalised, "evidence_ids"):
            continue
        records[argument_id] = record
    return records


def validate_argument(argument, evidence_index, run, results_dir=None) -> dict | None:
    """C1 v1.0: check current-run references before accepting an argument.

    The v1 callable boundary from ``interface-contracts.md``. Returns the
    **accepted record** — the argument's full identity plus its claim and the
    resolved evidence ids — or ``None`` when the submission is not acceptable.

    An argument is accepted only when every part of C1 holds:

    * it carries the run's **full identity** (``run_id``, ``ticker``,
      ``as_of_date`` all equal the ``RunContext``'s), so a foreign or
      identity-less submission is not this run's argument;
    * it has an ``argument_id`` and a nonempty ``claim``;
    * ``evidence_ids`` is a nonempty list, and **every** cited id resolves to
      admissible evidence in this run: present in the index, complete, and
      backed by retained material that exists and has content.

    A model flag is not acceptance, and a partially resolvable citation is not a
    partial acceptance: one unresolvable id refuses the argument. This is the
    validation layer; ``evaluate_publication`` rechecks the whole chain again,
    because a record can reach the index without passing through here.
    """
    if not isinstance(argument, dict):
        return None
    if _identity(argument, run) is None:
        return None
    argument_id = argument.get("argument_id") or argument.get("id")
    if not isinstance(argument_id, str) or not argument_id:
        return None
    claim = argument.get("claim") or argument.get("text") or ""
    if not isinstance(claim, str) or not claim.strip():
        return None
    evidence_ids = argument.get("evidence_ids")
    if not isinstance(evidence_ids, (list, tuple)) or not evidence_ids:
        return None
    if any(not isinstance(eid, str) or not eid for eid in evidence_ids):
        return None

    available = _evidence_records(evidence_index, run, results_dir)
    if any(eid not in available for eid in evidence_ids):
        return None

    return {
        "contract_version": str(argument.get("contract_version") or "1.0"),
        "run_id": run["run_id"],
        "ticker": run["ticker"],
        "as_of_date": run["as_of_date"],
        "argument_id": argument_id,
        "claim": claim,
        "speaker": argument.get("speaker", ""),
        "evidence_ids": list(evidence_ids),
    }


def _mapping_rows(index: dict, list_key: str, id_key: str):
    """``(key, record)`` pairs of a mapping index or of its legacy serialized form.

    Three shapes are read:

    * a bare ID -> record mapping yields its own items;
    * the authoritative v1 wrapper ``{"run_id": ..., list_key: {id: record}}``
      yields the wrapped mapping's items, so metadata is never mistaken for a
      record;
    * the legacy serialized form ``{list_key: [ {...id_key: ...} ]}`` is read
      from that list.

    The key a record is found under is a fallback only; the record's own ID field
    wins.
    """
    if list_key in index:
        wrapped = index[list_key]
        if isinstance(wrapped, dict):
            return list(wrapped.items())
        if isinstance(wrapped, list):
            return [(None, item) for item in wrapped]
    return list(index.items())


def _rating(value) -> str | None:
    """The canonical 5-tier rating for ``value``, or ``None`` when not publishable.

    Only the exact five tiers count. ``REVIEW``, casing variants, surrounding
    text ("Buy (small size)") and null are all invalid: free text is not a call.
    """
    if not isinstance(value, str):
        return None
    return value if value in _RATING_SET else None


def evaluate_publication(
    candidate, argument_index, evidence_index, run, results_dir=None
) -> PublicationResult:
    """C1 v1.0: the one deterministic publication result for a run.

    Rows are checked in the approved order, and the first matching row decides:

    1. C0 terminal failure / incomplete execution (``BUDGET_EXHAUSTED``,
       ``CONTEXT_TOO_LARGE`` keep their own code; anything not ``COMPLETED``,
       including a missing ``RunContext``, is ``RUN_NOT_COMPLETE``).
    2. An invalid rating (``INVALID_RATING``).
    3. Missing, unknown, cross-run or unaccepted references
       (``INSUFFICIENT_EVIDENCE``).
    4. Otherwise APPROVED, with the rating and the validated references.

    References are rechecked here, not taken from the model: a cited argument
    must exist in this run's ``argument_index``, ownership is decided by each
    record's full identity (never by an ID prefix), and each of its evidence ids
    must resolve in this run's ``evidence_index`` with its retained material still
    readable under ``results_dir``. A record with no retained material never
    resolves. BLOCKED always carries ``rating=None``.
    """
    run = run if isinstance(run, dict) else {}
    identity = {
        "contract_version": str(run.get("contract_version") or "1.0"),
        "run_id": run.get("run_id") or "",
        "ticker": run.get("ticker") or "",
        "as_of_date": run.get("as_of_date") or "",
    }

    def _blocked(*codes: str) -> PublicationResult:
        return PublicationResult(
            **identity, publication_status=BLOCKED, reason_codes=tuple(codes),
            rating=None, argument_ids=(), evidence_ids=(),
        )

    # Row 1: C0 execution state.
    status = run.get("execution_status")
    if status in _TERMINAL_EXECUTION_NAMED:
        return _blocked(status)
    if status != EXECUTION_COMPLETED:
        # FAILED, RUNNING and a missing RunContext: the workflow did not finish
        # normally, so nothing it produced may publish.
        return _blocked(RUN_NOT_COMPLETE)

    # Row 2: the rating must be one of the five tiers.
    candidate = candidate if isinstance(candidate, dict) else {}
    rating = _rating(candidate.get("rating"))
    if rating is None:
        return _blocked(INVALID_RATING)

    # Row 3: every cited reference must resolve inside this run.
    #
    # Fail-closed: a candidate is one recommendation, so an unresolvable cited
    # reference makes it unverifiable and the **whole** candidate is refused.
    # Skipping the references that happened to resolve would release a decision
    # whose stated basis is partly unverified (C1: "missing, unknown, cross-run or
    # unaccepted required references use INSUFFICIENT_EVIDENCE").
    arguments = _argument_records(argument_index, run)
    evidence = _evidence_records(evidence_index, run, results_dir)
    cited = [a for a in (candidate.get("argument_ids") or ()) if isinstance(a, str) and a]
    if not cited:
        return _blocked(INSUFFICIENT_EVIDENCE)
    resolved_arguments: list[str] = []
    resolved_evidence: list[str] = []
    chain: list[tuple[str, str, str]] = []
    for argument_id in cited:
        argument = arguments.get(argument_id)
        if argument is None:
            return _blocked(INSUFFICIENT_EVIDENCE)
        evidence_ids = [
            eid for eid in (argument.get("evidence_ids") or ())
            if isinstance(eid, str) and eid in evidence
        ]
        if not evidence_ids:
            return _blocked(INSUFFICIENT_EVIDENCE)
        if len(evidence_ids) != len(argument.get("evidence_ids") or ()):
            # The argument cites something that is not this run's admissible
            # evidence, even though its other references resolve.
            return _blocked(INSUFFICIENT_EVIDENCE)
        resolved_arguments.append(argument_id)
        for evidence_id in evidence_ids:
            if evidence_id not in resolved_evidence:
                resolved_evidence.append(evidence_id)
            chain.append((argument_id, evidence_id, str(evidence.get(evidence_id, {}).get("source", ""))))
    if not resolved_arguments or not resolved_evidence:
        return _blocked(INSUFFICIENT_EVIDENCE)

    # Row 4: approved, with identity, rating and validated references.
    return PublicationResult(
        **identity,
        publication_status=APPROVED,
        reason_codes=(),
        rating=rating,
        argument_ids=tuple(resolved_arguments),
        evidence_ids=tuple(resolved_evidence),
        resolved_chain=tuple(chain),
    )


def run_as_of_date(state: dict) -> str:
    """The run's effective cutoff date, as the ``RunContext`` records it.

    A researcher records an argument's identity with the same date the evidence
    records and the gate use — ``as_of()``'s own result — not the raw trade date,
    so the argument's identity and the evidence's identity agree.
    """
    course_run = state.get("course_run") if isinstance(state, dict) else None
    if isinstance(course_run, dict) and course_run.get("as_of_date"):
        return str(course_run["as_of_date"])
    from tradingagents.dataflows.date_window import as_of

    trade_date = state.get("trade_date") if isinstance(state, dict) else ""
    return as_of(trade_date, trade_date)


def accepted_arguments_view(argument_index: dict) -> list[dict]:
    """The legacy ``accepted_arguments`` list, derived from the authoritative mapping.

    The Portfolio Manager's prompt still lists accepted arguments in the old
    shape. It is built from ``argument_index`` on every write, so it cannot drift
    from the mapping, and the gate never reads it back as authority.
    """
    view = []
    for argument_id, record in (argument_index or {}).items():
        if not isinstance(record, dict):
            continue
        view.append({
            "argument_id": argument_id,
            "speaker": record.get("speaker", ""),
            "evidence_ids": list(record.get("evidence_ids") or ()),
        })
    return view


def publication_run(state: dict) -> dict:
    """The ``RunContext`` the gate judges a run against (C0).

    The graph state carries one complete ``course_run``, created once at the shared
    run entry. When it is absent the run has no identity to be checked against and
    no execution state to prove it finished, so ``execution_status`` is left unset
    and the gate blocks with ``RUN_NOT_COMPLETE``. A terminal failure recorded on
    the state (``BUDGET_EXHAUSTED`` / ``CONTEXT_TOO_LARGE``) is carried through so
    it keeps its own reason code.
    """
    if not isinstance(state, dict):
        return {}
    course_run = state.get("course_run")
    if isinstance(course_run, dict) and course_run.get("run_id"):
        return dict(course_run)
    recorded = state.get("execution_status")
    return {
        "contract_version": "1.0",
        "run_id": "",
        "ticker": state.get("company_of_interest") or "",
        "as_of_date": state.get("trade_date") or "",
        # No RunContext, no proof of completion: never assume COMPLETED. A
        # recorded terminal failure is carried through so it keeps its own code.
        "execution_status": recorded if recorded in _TERMINAL_EXECUTION else None,
        "request_limit": None,
    }


def publication_result_from_state(state: dict) -> PublicationResult | None:
    """The run's authoritative ``publication_result``, or ``None`` when it has none.

    A state carrying only the legacy flat ``publication_status`` (or legacy
    ``publication_chain``) has no publication result: that field is a projection
    of the gate's verdict, not the verdict, and a caller can set it freely.
    """
    stored = state.get("publication_result") if isinstance(state, dict) else None
    if not isinstance(stored, dict):
        return None
    if "publication_status" not in stored:
        return None
    return PublicationResult(
        contract_version=str(stored.get("contract_version") or "1.0"),
        run_id=stored.get("run_id") or "",
        ticker=stored.get("ticker") or "",
        as_of_date=stored.get("as_of_date") or "",
        publication_status=stored.get("publication_status"),
        reason_codes=tuple(stored.get("reason_codes") or ()),
        rating=stored.get("rating"),
        argument_ids=tuple(stored.get("argument_ids") or ()),
        evidence_ids=tuple(stored.get("evidence_ids") or ()),
        resolved_chain=tuple(tuple(link) for link in stored.get("resolved_chain") or ()),
    )


def apply_publication(result: PublicationResult, final_state: dict) -> dict:
    """Project a v1 ``PublicationResult`` onto the run state every sink reads.

    Writes ``publication_result`` (the authoritative record) plus the legacy
    projection fields the existing display/report adapters read. On APPROVED the
    candidate body becomes the official ``final_trade_decision`` and its rating the
    ``final_rating``. On BLOCKED the state carries no rating, no body, and no
    candidate fields at all.
    """
    final_state["publication_result"] = result.as_state()
    final_state["publication_status"] = result.publication_status
    final_state["publication_reason"] = result.reason
    final_state["publication_chain"] = [list(link) for link in result.resolved_chain]

    if result.approved:
        body = final_state.get("candidate_decision") or final_state.get("final_trade_decision") or ""
        final_state["final_rating"] = result.rating
        final_state["final_trade_decision"] = body
    else:
        final_state["final_rating"] = ""
        final_state["final_trade_decision"] = ""
    final_state.pop("candidate_decision", None)
    final_state.pop("candidate_rating", None)
    final_state.pop("candidate_argument_ids", None)
    return final_state
