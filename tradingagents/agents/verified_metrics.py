"""FR-02 owner module: verified metrics computed from validated operands.

Requirement: FR-02. Contracts: C0 (run identity) and C2 (verified metrics),
interface v1.0. Plan revision FR02-PLAN-01.

Public v1 callables (interface-contracts.md, "V1 callable boundaries"):

    verify_metric(request, run) -> MetricResult
    resolve_metric(metric_id, registry, run) -> VerifiedMetric or null

Rules this module enforces, from the contracts rather than from callers:

* Every record is scoped to the run that produced it. ``run_id``, ``ticker``
  and ``as_of_date`` come from the RunContext, never from the request and
  never from caller-supplied records.
* Arithmetic uses the original operands exactly (``decimal.Decimal``), so
  operand precision survives independently of later display rounding. Nothing
  is rounded to make a computation succeed and nothing is made absolute: a
  signed difference keeps the sign of ``current - reference``.
* YoY and ratio denominators must be greater than zero. A legal negative
  numerator (or negative current value for YoY) keeps its sign.
* Anything not verifiable is refused as UNVERIFIABLE with ``metric = None``
  and reason codes; a refused request registers nothing.
* Registration happens only inside a successful ``verify_metric``. Callers
  have no entry point to register or overwrite a trusted record. Re-posting an
  ID with identical content reuses the stored record; conflicting content
  keeps the original record.
* ``resolve_metric`` answers only from this run's registry, and only an ID
  whose stored content still matches what was verified.

No I/O, no model call, no transport.
"""

from decimal import Decimal, InvalidOperation

CONTRACT_VERSION = "1.0"

VERIFIED = "VERIFIED"
UNVERIFIABLE = "UNVERIFIABLE"

#: C0 RunContext fields copied onto each record, in a fixed order.
RUN_IDENTITY_FIELDS = ("run_id", "ticker", "as_of_date")

#: C2 VerifiedMetric fields beyond the shared identity.
FIELDS = (
    "contract_version",
    "metric_id",
    "kind",
    "operands",
    "result_value",
    "result_unit",
    "formula",
    "source_refs",
) + RUN_IDENTITY_FIELDS

#: Required operand roles per supported kind.
REQUIRED_ROLES = {
    "yoy": ("current", "prior"),
    "ratio": ("numerator", "denominator"),
    "price_delta": ("current", "reference"),
}

#: Formulas recorded on a VerifiedMetric.
FORMULAS = {
    "yoy": "100 * (current - prior) / prior",
    "ratio": "100 * numerator / denominator",
    "price_delta": "current - reference",
}

#: Roles that must be strictly positive for the kind to be verifiable.
POSITIVE_ROLE = {"yoy": "prior", "ratio": "denominator"}

PERIOD_KINDS = ("quarter", "year", "instant")

# --- Reason codes (stable strings, quotable without parsing prose) -------
REQ_NOT_MAPPING = "REQUEST_NOT_MAPPING"
REQ_KIND_UNKNOWN = "KIND_NOT_SUPPORTED"
REQ_OPERANDS_NOT_LIST = "OPERANDS_NOT_LIST"
REQ_OPERANDS_MISSING = "OPERANDS_MISSING"
REQ_OPERAND_NOT_MAPPING = "OPERAND_NOT_MAPPING"
REQ_ROLE_DUPLICATED = "OPERAND_ROLE_DUPLICATED"
REQ_ROLE_UNEXPECTED = "OPERAND_ROLE_UNEXPECTED"
RUN_IDENTITY_MISSING = "RUN_IDENTITY_MISSING"
OPERAND_ROLE_MISSING = "OPERAND_ROLE_MISSING"
OPERAND_VALUE_MISSING = "OPERAND_VALUE_MISSING"
OPERAND_VALUE_NONFINITE = "OPERAND_VALUE_NONFINITE"
OPERAND_UNIT_MISSING = "OPERAND_UNIT_MISSING"
OPERAND_PERIOD_MISSING = "OPERAND_PERIOD_MISSING"
OPERAND_PERIOD_INVALID = "OPERAND_PERIOD_INVALID"
OPERAND_PERIOD_UNKNOWN = "OPERAND_PERIOD_KIND_UNKNOWN"
OPERAND_FIELD_MISSING = "OPERAND_FIELD_REF_MISSING"
OPERAND_SOURCE_MISSING = "OPERAND_PROVENANCE_MISSING"
PERIODS_NOT_COMPARABLE = "PERIODS_NOT_COMPARABLE"
PERIODS_DIFFERENT = "PERIODS_DIFFERENT"
FIELDS_DIFFERENT = "FIELDS_DIFFERENT"
UNITS_INCOMPATIBLE = "UNITS_INCOMPATIBLE"
#: Dimensions that are never a price, whatever their capitalisation.
_NON_MONEY_UNITS = frozenset({"SHARES", "RATIO", "PERCENT"})

UNITS_NOT_A_PRICE = "PRICE_UNIT_NOT_A_CURRENCY"
DENOMINATOR_NOT_POSITIVE = "DENOMINATOR_NOT_POSITIVE"
COMPUTATION_INVALID = "COMPUTATION_INVALID"
REGISTRY_CONFLICT = "METRIC_ID_CONTENT_CONFLICT"

#: What the module keeps per run: {run_id: {metric_id: content_digest}}.
#: Only the IDs this module issued and the digest of the first registration
#: for each. Complete records are not retained here; resolve_metric takes the
#: record from the caller's registry and checks it against this digest. A run
#: sees only its own table.
_ISSUED = {}


def _copy(record):
    import copy

    return copy.deepcopy(record)


def _canonical(value):
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()





# --- Readers -------------------------------------------------------------


def _text(value):
    """Nonempty stripped text, or None."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _finite_decimal(value):
    """The value as an exact finite Decimal, or None.

    ``bool`` is refused although it subclasses ``int``; a float is taken via
    its shortest repr so binary representation error is not introduced here;
    a string keeps every digit it carries.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int):
        number = Decimal(value)
    elif isinstance(value, float):
        number = Decimal(repr(value))
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = Decimal(text)
        except (InvalidOperation, ValueError):
            return None
    else:
        return None
    return number if number.is_finite() else None


def _decimal_text(number):
    """A decimal string that keeps the computed value instead of rounding it."""
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("", "-0"):
        text = "0"
    return text


def _unit_measure(unit):
    """(scale, dimension) of a unit, per C2's "unit includes scale".

    ``USD_millions`` and ``EUR_millions`` share scale ``millions`` but are
    different dimensions. A missing or blank unit has no measure.
    """
    text = _text(unit)
    if text is None:
        return None
    lowered = text.lower()
    for scale in ("millions", "thousands", "billions"):
        suffix = "_" + scale
        if lowered.endswith(suffix) and len(lowered) > len(suffix):
            return (scale, text[: -len(suffix)])
    return ("", text)


def _is_currency(unit):
    """Whether a quote unit is a three-letter uppercase currency code, with scale.

    Recognises the code form this module's quotes use (``USD``, ``EUR``,
    optionally with a scale such as ``USD_millions``). A unit that scales and
    resolves to ``SHARES``, ``RATIO`` or ``PERCENT`` in any capitalisation is
    refused; so is anything that is not three uppercase ASCII letters. Only the
    spelling is checked; no external currency list is used.
    """
    measure = _unit_measure(unit)
    if measure is None:
        return False
    dimension = measure[1]
    if dimension.upper() in _NON_MONEY_UNITS:
        return False
    return len(dimension) == 3 and all("A" <= char <= "Z" for char in dimension)


def _units_compatible(left, right):
    left_measure, right_measure = _unit_measure(left), _unit_measure(right)
    if left_measure is None or right_measure is None:
        return False
    return left_measure == right_measure


def _iso_date(value):
    """An ISO YYYY-MM-DD calendar date as an ordinal, or None."""
    import datetime

    text = _text(value)
    if text is None or len(text) != 10 or text[4] != "-" or text[7] != "-":
        return None
    parts = text.split("-")
    if not all(part.isdigit() for part in parts):
        return None
    try:
        return datetime.date(int(parts[0]), int(parts[1]), int(parts[2])).toordinal()
    except ValueError:
        return None


def _period(period):
    """(kind, start ordinal, end ordinal) or a reason code.

    Needs an ISO start and end, a nonempty label and a kind matching the span.
    A calendar quarter runs from a month's first day to a month's last day and
    covers exactly 3 whole months; a fiscal year covers exactly 12. A week-based
    (4-4-5) quarter is exactly 91 or 98 days and a week-based year exactly 364
    or 371. An instant is one day. Anything else, including a single day
    labelled a year or a quarter, is refused before any comparison.
    """
    import calendar
    import datetime

    if not isinstance(period, dict):
        return OPERAND_PERIOD_MISSING
    kind = _text(period.get("kind"))
    if kind is None:
        return OPERAND_PERIOD_MISSING
    if kind not in PERIOD_KINDS:
        return OPERAND_PERIOD_UNKNOWN
    if _text(period.get("label")) is None:
        return OPERAND_PERIOD_MISSING
    start, end = _iso_date(period.get("start")), _iso_date(period.get("end"))
    if start is None or end is None or end < start:
        return OPERAND_PERIOD_INVALID

    if kind == "instant":
        return (kind, start, end) if start == end else OPERAND_PERIOD_INVALID

    first = datetime.date.fromordinal(start)
    last = datetime.date.fromordinal(end)
    days = end - start + 1

    whole_months = 0
    if first.day == 1 and last.day == calendar.monthrange(last.year, last.month)[1]:
        whole_months = (last.year - first.year) * 12 + (last.month - first.month) + 1

    if kind == "quarter":
        if whole_months == 3 or days in (91, 98):
            return (kind, start, end)
        return OPERAND_PERIOD_INVALID
    if whole_months == 12 or days in (364, 371):
        return (kind, start, end)
    return OPERAND_PERIOD_INVALID


def _about_one_year(earlier, later):
    """True when ``later`` is ``earlier``'s anniversary, give or take a week."""
    import datetime

    first = datetime.date.fromordinal(min(earlier, later))
    second = datetime.date.fromordinal(max(earlier, later))
    try:
        anniversary = first.replace(year=first.year + 1)
    except ValueError:                      # 29 February
        anniversary = first.replace(year=first.year + 1, day=28)
    return abs((second - anniversary).days) <= 7


def _comparable_periods(prior, current):
    """Whether two YoY periods compare the same field over comparable spans.

    Only a full year against the full year before it, or a fiscal quarter
    against the same quarter a year earlier, qualifies. Two quote instants do
    not: a same-day pair of prices is a gap, never a YoY change.
    """
    prior_kind, prior_start, prior_end = prior
    current_kind, current_start, current_end = current
    if prior_kind != current_kind or prior_kind == "instant":
        return False
    if current_end <= prior_end:
        return False
    return _about_one_year(prior_end, current_end) and _about_one_year(
        prior_start, current_start)


def _run_identity(run):
    """The three identity fields of a RunContext, or a reason code."""
    if not isinstance(run, dict):
        return RUN_IDENTITY_MISSING
    identity = {}
    for field in RUN_IDENTITY_FIELDS:
        value = _text(run.get(field))
        if value is None:
            return RUN_IDENTITY_MISSING
        identity[field] = value
    return identity


def _same_run(record, identity):
    return all(record.get(field) == identity[field] for field in RUN_IDENTITY_FIELDS)


def _dedupe(codes):
    ordered = []
    for code in codes:
        if code not in ordered:
            ordered.append(code)
    return ordered


# --- Operand validation --------------------------------------------------


def _read_operands(raw_operands):
    """Validate the C2 Operand list; return ({role: operand}, reasons) or a code."""
    if not isinstance(raw_operands, (list, tuple)):
        return [REQ_OPERANDS_NOT_LIST]
    if not raw_operands:
        return [REQ_OPERANDS_MISSING]

    reasons = []
    by_role = {}
    for raw in raw_operands:
        if not isinstance(raw, dict):
            reasons.append(REQ_OPERAND_NOT_MAPPING)
            continue
        role = _text(raw.get("role"))
        if role is None:
            reasons.append(OPERAND_ROLE_MISSING)
            continue
        if role in by_role:
            reasons.append(REQ_ROLE_DUPLICATED)
            continue

        raw_value = raw.get("value")
        value = _finite_decimal(raw_value)
        if value is None:
            reasons.append(
                OPERAND_VALUE_MISSING if _text(raw_value) is None
                else OPERAND_VALUE_NONFINITE)
        if _text(raw.get("unit")) is None:
            reasons.append(OPERAND_UNIT_MISSING)
        span = _period(raw.get("period"))
        if isinstance(span, str):
            reasons.append(span)
        if _text(raw.get("field_ref")) is None:
            reasons.append(OPERAND_FIELD_MISSING)
        if _text(raw.get("source_ref")) is None:
            reasons.append(OPERAND_SOURCE_MISSING)

        by_role[role] = {
            "operand": {
                "role": role,
                "value": raw_value,
                "unit": _text(raw.get("unit")) if raw.get("unit") is not None else None,
                "period": _copy(raw.get("period")),
                "source_ref": _text(raw.get("source_ref")),
                "field_ref": _text(raw.get("field_ref")),
            },
            "decimal": value,
            "span": span,
        }
    if reasons:
        return _dedupe(reasons)
    return by_role


def _pair_checks(kind, by_role):
    """Kind-specific role, period, field and unit rules; returns reason codes.

    YoY: the same financial field, one complete year or fiscal quarter against
    the period a year earlier. Ratio: one shared period. Price gap: two prices
    from one quote instant with the same start and end, in compatible units,
    and both quoted in a currency rather than shares or a dimensionless ratio.
    """
    roles = REQUIRED_ROLES[kind]
    reasons = []
    for role in roles:
        if role not in by_role:
            reasons.append(OPERAND_ROLE_MISSING)
    for role in by_role:
        if role not in roles:
            reasons.append(REQ_ROLE_UNEXPECTED)
    if reasons:
        return _dedupe(reasons)

    first, second = by_role[roles[0]], by_role[roles[1]]
    for side in (first, second):
        if side["decimal"] is None:
            return [OPERAND_VALUE_NONFINITE]
        if isinstance(side["span"], str):
            return [side["span"]]

    if not _units_compatible(first["operand"]["unit"], second["operand"]["unit"]):
        reasons.append(UNITS_INCOMPATIBLE)

    if kind == "yoy":
        if first["operand"]["field_ref"] != second["operand"]["field_ref"]:
            reasons.append(FIELDS_DIFFERENT)
        if not _comparable_periods(second["span"], first["span"]):
            reasons.append(PERIODS_NOT_COMPARABLE)
    elif kind == "ratio":
        if first["span"] != second["span"]:
            reasons.append(PERIODS_DIFFERENT)
    else:
        current_span, reference_span = first["span"], second["span"]
        if current_span[0] != "instant" or reference_span[0] != "instant":
            reasons.append(PERIODS_NOT_COMPARABLE)
        elif current_span[1:] != reference_span[1:]:
            reasons.append(PERIODS_DIFFERENT)
        if not (_is_currency(first["operand"]["unit"])
                and _is_currency(second["operand"]["unit"])):
            reasons.append(UNITS_NOT_A_PRICE)

    if kind in POSITIVE_ROLE and by_role[POSITIVE_ROLE[kind]]["decimal"] <= 0:
        reasons.append(DENOMINATOR_NOT_POSITIVE)
    return _dedupe(reasons)


# --- Computation ---------------------------------------------------------


def _compute(kind, by_role):
    """(Decimal result, result unit) or a reason code list.

    Decimal arithmetic can still raise on an extreme exponent or an undefined
    operation; that is reported as an UNVERIFIABLE reason, never as a verified
    value and never as an exception to the caller.
    """
    roles = REQUIRED_ROLES[kind]
    first = by_role[roles[0]]["decimal"]
    second = by_role[roles[1]]["decimal"]
    try:
        if kind == "yoy":
            return Decimal(100) * (first - second) / second, "%"
        if kind == "ratio":
            return Decimal(100) * first / second, "%"
        return first - second, by_role["current"]["operand"]["unit"]
    except (ArithmeticError, InvalidOperation, ValueError, OverflowError):
        return [COMPUTATION_INVALID]


# --- Registration --------------------------------------------------------


def _metric_id(identity, kind, operands):
    """An opaque, deterministic ID over this run's identity and the operands.

    The same run with the same operands always yields the same ID; different
    operands never share one. Callers must not read meaning from the spelling.
    """
    return "metric-" + _canonical({
        "contract_version": CONTRACT_VERSION,
        "run": {field: identity[field] for field in RUN_IDENTITY_FIELDS},
        "kind": kind,
        "operands": operands,
    })[:32]


def _issue(identity, metric):
    """Record this run's issued metric_id and the first registration's digest.

    ``setdefault`` fixes the first digest before any comparison, so two
    analysts registering at the same time cannot overwrite it. Returns the
    metric_id on first registration and on an identical re-post, and None on
    conflict, where the first digest stands.
    """
    table = _ISSUED.setdefault(identity["run_id"], {})
    digest = _canonical({key: metric[key] for key in FIELDS})
    existing = table.setdefault(metric["metric_id"], digest)
    if existing == digest:
        return metric["metric_id"]
    return None


def _expected_digest(metric_id, identity):
    """The first registered digest for this run's own ID, or None."""
    table = _ISSUED.get(identity["run_id"])
    if not table:
        return None
    digest = table.get(metric_id)
    return digest if isinstance(digest, str) and digest else None


def _release_run(run):
    """Forget this run's issued IDs and digests; the run's records are dropped.

    Called by the graph once a run is finished so a later run does not inherit
    an earlier one's IDs. Idempotent; returns whether anything was released.
    """
    identity = _run_identity(run)
    if isinstance(identity, str):
        return False
    return _ISSUED.pop(identity["run_id"], None) is not None


def _result(status, metric, reasons):
    return {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "metric": _copy(metric) if metric is not None else None,
        "reason_codes": _dedupe(reasons),
    }


def _unverifiable(reasons):
    return _result(UNVERIFIABLE, None, reasons or [REQ_OPERANDS_MISSING])


# --- Public boundary -----------------------------------------------------


def verify_metric(request, run):
    """Compute one metric from validated operands and register it when verified.

    Args:
        request: a C2 MetricRequest ``{"kind", "operands"}`` whose operands are
            C2 Operand mappings (role, value, unit, period, source_ref,
            field_ref). Read only.
        run: a C0 RunContext. ``run_id``, ``ticker`` and ``as_of_date`` are
            copied onto the record to scope it to this run. Read only.

    Returns:
        A C2 MetricResult. VERIFIED carries a VerifiedMetric and no reason
        codes; UNVERIFIABLE carries ``metric = None`` and at least one reason
        code, and registers nothing.
    """
    if not isinstance(request, dict):
        return _unverifiable([REQ_NOT_MAPPING])
    kind = _text(request.get("kind"))
    if kind is None or kind not in REQUIRED_ROLES:
        return _unverifiable([REQ_KIND_UNKNOWN])

    identity = _run_identity(run)
    if isinstance(identity, str):
        return _unverifiable([identity])

    by_role = _read_operands(request.get("operands"))
    if isinstance(by_role, list):
        return _unverifiable(by_role)

    reasons = _pair_checks(kind, by_role)
    if reasons:
        return _unverifiable(reasons)

    outcome = _compute(kind, by_role)
    if isinstance(outcome, list):
        return _unverifiable(outcome)
    value, unit = outcome
    if not value.is_finite():
        return _unverifiable([COMPUTATION_INVALID])

    operands = [by_role[role]["operand"] for role in REQUIRED_ROLES[kind]]
    sources = []
    for operand in operands:
        if operand["source_ref"] not in sources:
            sources.append(operand["source_ref"])

    metric = {
        "contract_version": CONTRACT_VERSION,
        "metric_id": _metric_id(identity, kind, operands),
        "kind": kind,
        "operands": operands,
        "result_value": _decimal_text(value),
        "result_unit": unit,
        "formula": FORMULAS[kind],
        "source_refs": sources,
    }
    for field in RUN_IDENTITY_FIELDS:
        metric[field] = identity[field]

    metric_id = _issue(identity, metric)
    if metric_id is None:
        # Same ID, different content: the first digest stands and this
        # request is not honoured as a new verified value.
        return _unverifiable([REGISTRY_CONFLICT])
    return _result(VERIFIED, metric, [])


def resolve_metric(metric_id, registry, run):
    """Resolve a trusted ID to an independent copy of its VerifiedMetric.

    The record is taken from the caller's registry, then accepted only when
    this run issued that ID, the record is complete and scoped to this run,
    and its content matches the digest of the first registration. An empty
    registry, a missing ID, an invented ID, an ID from another run or a
    modified value all return ``None``. ``registry`` is only read.
    """
    candidate = _text(metric_id)
    if candidate is None:
        return None
    identity = _run_identity(run)
    if isinstance(identity, str):
        return None

    offered = None
    if isinstance(registry, dict):
        raw = registry.get(candidate)
        offered = raw if isinstance(raw, dict) else None
    elif isinstance(registry, (list, tuple)):
        for record in registry:
            if isinstance(record, dict) and record.get("metric_id") == candidate:
                offered = record
                break
    if offered is None or any(key not in offered for key in FIELDS):
        return None

    expected = _expected_digest(candidate, identity)
    if expected is None:
        return None
    if not _same_run(offered, identity):
        return None
    if offered.get("contract_version") != CONTRACT_VERSION:
        return None
    if _canonical({key: offered[key] for key in FIELDS}) != expected:
        return None
    return {key: _copy(offered[key]) for key in FIELDS}
