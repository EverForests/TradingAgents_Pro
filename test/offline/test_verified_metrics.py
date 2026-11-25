"""FR-02 C0/C2 offline checks: synthetic operands for the five D1 case IDs.

Plan revision: FR02-PLAN-01 (base 3d5ce62, interface v1.0).
Requirement: FR-02. Contracts: C0 (run identity) and C2 (verified metrics).

The cases assert the boundaries agreed in interface-contracts.md, "V1
callable boundaries":

    verify_metric(request, run) -> MetricResult
    resolve_metric(metric_id, registry, run) -> VerifiedMetric or null

The owner module is not implemented yet, so it is imported inside each test
instead of at module import time: pytest collects this file on the unmodified
baseline. A missing module is a setup gap, not the behavioural failure this
plan asks for. The real-graph baseline failure is still to be added.

Every operand below is synthetic. The D4 synthetic controls are kept exactly
(100 -> 125, 20/80, 10.125 - 5.599 and its reverse); the NVDA, AAPL and MSFT
real-company operands are unfrozen and are not used or counted as passing.

Only what the product returns is used as evidence. This file never builds an
empty registry or a hand-assembled mapping and calls it proof that the product
registered or refused a record; those need the real registration path and are
listed as pending at the end of the file.
"""

from decimal import Decimal

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import Field as _PydanticField

PERCENT_TOLERANCE = Decimal("0.1")     # percentage points, not relative percent
PRICE_TOLERANCE = Decimal("0.01")      # price units

CONTRACT_VERSION = "1.0"
RUN_ID = "run-fr02-synthetic-0001"
TICKER = "SYN"
AS_OF = "2026-11-10"

SOURCE_REF = "fixture:fr02-synthetic-controls"
FIELD_CURRENT = "synthetic.current"
FIELD_PRIOR = "synthetic.prior"


# --- Contracts: run identity, periods and operands -----------------------


def _owner():
    """The FR-02 owner module, imported at call time so collection never fails."""
    from tradingagents.agents import verified_metrics

    return verified_metrics


def _run(run_id=RUN_ID):
    """A C0 RunContext: contract version, run identity, ticker, date and state."""
    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "ticker": TICKER,
        "as_of_date": AS_OF,
        "execution_status": "RUNNING",
        "request_limit": 40,
    }


def _period(kind, start, end, label):
    """A C2 Operand.period: {kind, start, end, label}."""
    return {"kind": kind, "start": start, "end": end, "label": label}


# Comparable full years, both ending before the 2026-11-10 analysis date.
FY_PERIOD = _period("year", "2025-06-01", "2026-05-31", "FY2026")
PRIOR_FY_PERIOD = _period("year", "2024-06-01", "2025-05-31", "FY2025")
# A year that is not adjacent to FY2026.
UNRELATED_FY_PERIOD = _period("year", "2023-06-01", "2024-05-31", "FY2024")
# One fiscal quarter and the same quarter a year earlier.
QUARTER_PERIOD = _period("quarter", "2026-03-01", "2026-05-31", "FY2026 Q4")
PRIOR_QUARTER_PERIOD = _period("quarter", "2025-03-01", "2025-05-31", "FY2025 Q4")
# Two quote instants.
QUOTE_PERIOD = _period("instant", "2026-11-10", "2026-11-10", "2026-11-10 close")
OTHER_QUOTE_PERIOD = _period("instant", "2026-11-09", "2026-11-09", "2026-11-09 close")


def _operand(role, value, unit, period, field_ref):
    """A C2 Operand with explicit provenance, unit, period and field."""
    return {
        "role": role,
        "value": value,
        "unit": unit,
        "period": dict(period),
        "source_ref": SOURCE_REF,
        "field_ref": field_ref,
    }


def _request(kind, operands):
    return {"kind": kind, "operands": list(operands)}


def _yoy(current, prior, current_unit="USD_millions", prior_unit="USD_millions",
         current_period=FY_PERIOD, prior_period=PRIOR_FY_PERIOD,
         field_ref=FIELD_CURRENT):
    """One financial field measured in two comparable adjacent periods."""
    return _request("yoy", [
        _operand("current", current, current_unit, current_period, field_ref),
        _operand("prior", prior, prior_unit, prior_period, field_ref),
    ])


def _ratio(numerator, denominator, numerator_unit="USD_millions",
           denominator_unit="USD_millions", numerator_period=FY_PERIOD,
           denominator_period=FY_PERIOD):
    return _request("ratio", [
        _operand("numerator", numerator, numerator_unit, numerator_period, FIELD_CURRENT),
        _operand("denominator", denominator, denominator_unit, denominator_period, FIELD_PRIOR),
    ])


def _delta(current, reference, current_unit="USD", reference_unit="USD",
           current_period=QUOTE_PERIOD, reference_period=QUOTE_PERIOD):
    return _request("price_delta", [
        _operand("current", current, current_unit, current_period, "synthetic.boll_ub"),
        _operand("reference", reference, reference_unit, reference_period, "synthetic.close"),
    ])


# --- Reading a product result -------------------------------------------


def _verified(result):
    """The VERIFIED MetricResult, failing clearly on anything else."""
    assert result is not None, "verify_metric returned None instead of a MetricResult"
    assert result.get("status") == "VERIFIED", (
        f"expected VERIFIED, got {result.get('status')!r} "
        f"with reason codes {result.get('reason_codes')!r}"
    )
    metric = result.get("metric")
    assert metric is not None, "a VERIFIED result carries no VerifiedMetric"
    return metric


def _value(metric):
    """The result_value as a Decimal, requiring the decimal-string form."""
    value = metric.get("result_value")
    assert isinstance(value, str), (
        f"result_value must be a decimal string, got {type(value).__name__}"
    )
    return Decimal(value)


def _assert_unverifiable(result):
    """UNVERIFIABLE: at least one reason code and no verified value."""
    assert result is not None, "verify_metric returned None instead of a MetricResult"
    assert result.get("status") == "UNVERIFIABLE", (
        f"expected UNVERIFIABLE, got {result.get('status')!r}"
    )
    assert result.get("metric") is None, (
        "an UNVERIFIABLE result must not carry a VerifiedMetric"
    )
    assert result.get("reason_codes"), "UNVERIFIABLE must state at least one reason code"


def _assert_provenance(metric, run, request):
    """This run's identity, and every operand's provenance, field and period.

    Operands are matched one role at a time so two periods that happen to be
    equal dictionaries are still compared rather than collapsed. ``source_refs``
    must be nonempty and cover the input sources; order is not fixed.
    """
    assert metric.get("run_id") == run["run_id"], "the record is not scoped to this run"
    assert metric.get("ticker") == run["ticker"], "the record carries another ticker"
    assert metric.get("as_of_date") == run["as_of_date"], "the record carries another as_of_date"
    assert metric.get("metric_id"), "a VERIFIED record needs a metric_id"
    assert metric.get("kind") == request["kind"]
    recorded_sources = metric.get("source_refs")
    assert recorded_sources, "a VERIFIED record must retain source_refs"
    assert set(recorded_sources) == {o["source_ref"] for o in request["operands"]}, (
        "source_refs do not match the operands' provenance"
    )
    operands = metric.get("operands")
    assert operands, "a VERIFIED record must retain its operands"
    by_role = {}
    for operand in operands:
        by_role.setdefault(operand.get("role"), []).append(operand)
    for expected in request["operands"]:
        role = expected["role"]
        assert len(by_role.get(role, [])) == 1, f"expected exactly one {role!r} operand"
        actual = by_role[role][0]
        assert actual.get("value") == expected["value"], f"{role} value altered"
        assert actual.get("unit") == expected["unit"], f"{role} unit altered"
        assert actual.get("field_ref") == expected["field_ref"], f"{role} field altered"
        assert actual.get("source_ref") == expected["source_ref"], f"{role} provenance altered"
        assert actual.get("period") == expected["period"], f"{role} period altered"


def _assert_same_record(resolved, metric, run):
    """A resolved record matches the verified one on identity, value and provenance."""
    assert resolved is not None, "resolve_metric returned None for a verified ID"
    for field in ("run_id", "metric_id", "kind", "result_value", "result_unit", "formula"):
        assert resolved.get(field) == metric.get(field), f"{field} differs"
    assert resolved.get("ticker") == run["ticker"], "the resolved record carries another ticker"
    assert resolved.get("as_of_date") == run["as_of_date"], (
        "the resolved record carries another as_of_date"
    )
    assert resolved.get("operands") == metric.get("operands"), "operands differ"
    sources = resolved.get("source_refs")
    assert sources, "the resolved record must retain source_refs"
    assert set(sources) == set(metric.get("source_refs") or []), "source_refs differ"


# --- T-FR02-YOY: YoY = 100 * (current / prior - 1) -----------------------
# Adjacent-year comparable periods only. The prior must be > 0 in this
# release; the current may be negative and keeps its sign.


def test_fr02_yoy_synthetic_control_100_to_125():
    """T-FR02-YOY: D4 synthetic control, one field, two comparable years."""
    run = _run()
    request = _yoy("125", "100")
    metric = _verified(_owner().verify_metric(request, run))
    value = _value(metric)
    assert abs(value - Decimal("25")) <= PERCENT_TOLERANCE, (
        f"{value}% is outside 0.1 percentage points"
    )
    assert metric.get("result_unit") == "%"
    _assert_provenance(metric, run, request)


def test_fr02_yoy_adjacent_year_same_quarter():
    """T-FR02-YOY: the same fiscal quarter one year apart is comparable."""
    run = _run()
    request = _yoy("125", "100", current_period=QUARTER_PERIOD,
                   prior_period=PRIOR_QUARTER_PERIOD)
    metric = _verified(_owner().verify_metric(request, run))
    value = _value(metric)
    assert abs(value - Decimal("25")) <= PERCENT_TOLERANCE
    _assert_provenance(metric, run, request)


def test_fr02_yoy_negative_current_keeps_sign():
    """T-FR02-YOY: a negative current is legal and is not rejected."""
    request = _yoy("-50", "100")
    metric = _verified(_owner().verify_metric(request, _run()))
    value = _value(metric)
    assert value < 0, "a negative current must not be dropped or made positive"
    assert abs(value - Decimal("-150")) <= PERCENT_TOLERANCE


@pytest.mark.parametrize("prior", ["0", "-100"])
def test_fr02_yoy_nonpositive_prior_is_unverifiable(prior):
    """T-FR02-YOY / T-FR02-INVALID: the prior must be > 0."""
    _assert_unverifiable(_owner().verify_metric(_yoy("125", prior), _run()))


def test_fr02_yoy_unrelated_year_periods_are_unverifiable():
    """T-FR02-YOY / T-FR02-INVALID: adjacent comparable periods are required."""
    _assert_unverifiable(
        _owner().verify_metric(_yoy("125", "100", prior_period=UNRELATED_FY_PERIOD), _run())
    )


def test_fr02_yoy_currency_mismatch_is_unverifiable():
    """T-FR02-YOY / T-FR02-INVALID: USD_millions against EUR_millions."""
    _assert_unverifiable(
        _owner().verify_metric(_yoy("125", "100", prior_unit="EUR_millions"), _run())
    )


def test_fr02_yoy_amount_against_ratio_dimension_is_unverifiable():
    """T-FR02-YOY / T-FR02-INVALID: an amount compared with a dimensionless ratio."""
    _assert_unverifiable(
        _owner().verify_metric(_yoy("125", "100", prior_unit="ratio"), _run())
    )


# --- T-FR02-RATIO: Ratio = 100 * numerator / denominator -----------------
# The denominator must be > 0; the numerator may be negative and keeps its
# sign. Unit compatibility and period alignment are recorded.


def test_fr02_ratio_synthetic_control_20_over_80():
    """T-FR02-RATIO: D4 synthetic control, same period and unit."""
    run = _run()
    request = _ratio("20", "80")
    metric = _verified(_owner().verify_metric(request, run))
    value = _value(metric)
    assert abs(value - Decimal("25")) <= PERCENT_TOLERANCE
    assert metric.get("result_unit") == "%"
    _assert_provenance(metric, run, request)


def test_fr02_ratio_negative_numerator_is_minus_25():
    """T-FR02-RATIO: -20/80 is -25%; the sign is preserved."""
    value = _value(_verified(_owner().verify_metric(_ratio("-20", "80"), _run())))
    assert value < 0, "a negative numerator must not be replaced by abs()"
    assert abs(value - Decimal("-25")) <= PERCENT_TOLERANCE


@pytest.mark.parametrize("denominator", ["0", "-80"])
def test_fr02_ratio_nonpositive_denominator_is_unverifiable(denominator):
    """T-FR02-RATIO / T-FR02-INVALID: the denominator must be > 0."""
    _assert_unverifiable(_owner().verify_metric(_ratio("20", denominator), _run()))


def test_fr02_ratio_period_mismatch_is_unverifiable():
    """T-FR02-RATIO / T-FR02-INVALID: the operands cover different periods."""
    _assert_unverifiable(
        _owner().verify_metric(_ratio("20", "80", denominator_period=PRIOR_FY_PERIOD), _run())
    )


def test_fr02_ratio_currency_mismatch_is_unverifiable():
    """T-FR02-RATIO / T-FR02-INVALID: USD_millions against EUR_millions."""
    _assert_unverifiable(
        _owner().verify_metric(_ratio("20", "80", denominator_unit="EUR_millions"), _run())
    )


def test_fr02_ratio_dimension_mismatch_is_unverifiable():
    """T-FR02-RATIO / T-FR02-INVALID: a currency amount over a share count."""
    _assert_unverifiable(
        _owner().verify_metric(_ratio("20", "80", denominator_unit="shares"), _run())
    )


# --- T-FR02-DELTA: signed difference = current - reference ---------------
# The sign and the price unit are preserved; nothing is made absolute.


def test_fr02_delta_synthetic_control_10_125_minus_5_599():
    """T-FR02-DELTA: D4 synthetic control, positive direction."""
    run = _run()
    request = _delta("10.125", "5.599")
    metric = _verified(_owner().verify_metric(request, run))
    value = _value(metric)
    assert abs(value - Decimal("4.526")) <= PRICE_TOLERANCE, (
        f"{value} is outside 0.01 price units"
    )
    assert value > 0
    assert metric.get("result_unit") == "USD"
    _assert_provenance(metric, run, request)


def test_fr02_delta_reversed_operands_are_minus_4_526():
    """T-FR02-DELTA: reversing the roles negates the result."""
    value = _value(_verified(_owner().verify_metric(_delta("5.599", "10.125"), _run())))
    assert value < 0, "an absolute-value implementation fails this case"
    assert abs(value - Decimal("-4.526")) <= PRICE_TOLERANCE


def test_fr02_delta_currency_mismatch_is_unverifiable():
    """T-FR02-DELTA / T-FR02-INVALID: a USD price against a EUR price."""
    _assert_unverifiable(
        _owner().verify_metric(_delta("10.125", "5.599", reference_unit="EUR"), _run())
    )


def test_fr02_delta_dimension_mismatch_is_unverifiable():
    """T-FR02-DELTA / T-FR02-INVALID: a currency amount against a share count."""
    _assert_unverifiable(
        _owner().verify_metric(_delta("10.125", "5.599", reference_unit="shares"), _run())
    )


def test_fr02_delta_different_quotes_are_unverifiable():
    """T-FR02-DELTA / T-FR02-INVALID: operands from different quotes."""
    _assert_unverifiable(
        _owner().verify_metric(
            _delta("10.125", "5.599", reference_period=OTHER_QUOTE_PERIOD), _run()
        )
    )


# --- T-FR02-INVALID: rejected before any verified value -----------------


@pytest.mark.parametrize("bad_value", ["NaN", "Infinity", "-inf", "nan"])
def test_fr02_invalid_nonfinite_operand_is_unverifiable(bad_value):
    """T-FR02-INVALID: nonfinite operands never become a verified value."""
    _assert_unverifiable(_owner().verify_metric(_yoy(bad_value, "100"), _run()))


def test_fr02_invalid_missing_provenance_is_unverifiable():
    """T-FR02-INVALID: an operand without source_ref has no provenance."""
    request = _yoy("125", "100")
    request["operands"][1]["source_ref"] = ""
    _assert_unverifiable(_owner().verify_metric(request, _run()))


def test_fr02_invalid_missing_operand_role_is_unverifiable():
    """T-FR02-INVALID: a required operand role is absent."""
    request = _yoy("125", "100")
    request["operands"] = [request["operands"][0]]
    _assert_unverifiable(_owner().verify_metric(request, _run()))


def test_fr02_invalid_unknown_kind_is_unverifiable():
    """T-FR02-INVALID: narrative arithmetic out of scope is not a kind."""
    _assert_unverifiable(_owner().verify_metric(_request("basis_points", []), _run()))


# --- T-FR02-IDENTITY: run_id + metric_id + content ----------------------
# A verified record carries its run identity, and resolution compares the whole
# record. Unknown, forged and cross-run IDs resolve to None; a tampered value
# is never accepted, though returning the trusted record is.


def test_fr02_identity_verified_record_is_scoped_to_this_run():
    """T-FR02-IDENTITY / C0: the record carries this run's identity."""
    run = _run()
    metric = _verified(_owner().verify_metric(_yoy("125", "100"), run))
    assert metric.get("run_id") == run["run_id"]
    assert metric.get("ticker") == run["ticker"]
    assert metric.get("as_of_date") == run["as_of_date"]
    assert metric.get("metric_id")


def test_fr02_identity_resolves_by_content():
    """T-FR02-IDENTITY: the verified ID resolves to the same record."""
    owner = _owner()
    run = _run()
    metric = _verified(owner.verify_metric(_yoy("125", "100"), run))
    registry = {metric["metric_id"]: metric}
    _assert_same_record(owner.resolve_metric(metric["metric_id"], registry, run), metric, run)


def test_fr02_identity_unknown_id_returns_none():
    """T-FR02-IDENTITY: an ID the product never issued resolves to None."""
    owner = _owner()
    run = _run()
    metric = _verified(owner.verify_metric(_yoy("125", "100"), run))
    registry = {metric["metric_id"]: metric}
    assert owner.resolve_metric("metric-never-issued", registry, run) is None


def test_fr02_identity_tampered_value_is_never_accepted():
    """T-FR02-IDENTITY: None, or the trusted record compared in full."""
    owner = _owner()
    run = _run()
    metric = _verified(owner.verify_metric(_yoy("125", "100"), run))
    changed = {key: (list(value) if isinstance(value, list) else value)
               for key, value in metric.items()}
    changed["result_value"] = "999"
    resolved = owner.resolve_metric(metric["metric_id"], {metric["metric_id"]: changed}, run)
    if resolved is not None:
        _assert_same_record(resolved, metric, run)


def test_fr02_identity_forged_id_returns_none():
    """T-FR02-IDENTITY: an invented ID the product never issued resolves to None."""
    owner = _owner()
    run = _run()
    metric = _verified(owner.verify_metric(_yoy("125", "100"), run))
    forged = dict(metric)
    forged["metric_id"] = "metric-self-declared"
    forged["result_value"] = "999"
    assert owner.resolve_metric("metric-self-declared",
                                {forged["metric_id"]: forged}, run) is None


def test_fr02_identity_prior_run_id_returns_none():
    """T-FR02-IDENTITY / C0: IDs never resolve from another run."""
    owner = _owner()
    metric = _verified(owner.verify_metric(_yoy("125", "100"), _run()))
    registry = {metric["metric_id"]: metric}
    run_b = _run("run-fr02-synthetic-0002")
    assert owner.resolve_metric(metric["metric_id"], registry, run_b) is None


# --- Pending: needs the real registration path (not asserted here) ------
# Listed so the gap is explicit; none of these is disguised as a pass.
#
# 1. A rejected request leaving no entry in the run registry: needs the real
#    run registry owned by the product, not a dictionary built by this test.
# 2. Repeated and conflicting writes under one metric_id: two different
#    computations may legitimately carry different IDs, so conflict semantics
#    need the product's explicit write/registration entry point.
# 3. Controlled downstream field and final metrics table resolving the same
#    metric_id, value and unit: needs the real graph and report writer.
# 4. The real-graph baseline failure (Propagator initial state, real
#    GraphSetup.setup_graph, market and fundamentals subgraphs, tool nodes,
#    Portfolio Manager, write_report_tree(html=False)): blocked because the
#    reads of tradingagents/agents/tools/__init__.py,
#    tradingagents/agents/analysts/market_analyst.py and
#    tradingagents/agents/__init__.py were denied. The report heading is not
#    fixed, so no title is asserted.
# 5. The four real-company examples stay unfrozen and are not counted here.


# --- Real graph, fixed model, fixed data (normal path) ------------------
# The whole graph runs: the run's initial state, the market and fundamentals
# analyst subgraphs, their tool nodes, the Portfolio Manager and the report
# writer, with every provider and vendor answered offline. Nothing is written
# into the state by hand and no model text stands in for a tool return.
#
# Data shapes follow the retained tool returns: the market snapshot prints a
# "Field | Value" table before a Date/Close history, and the income statement
# prints a CSV whose Period column holds fiscal year ends. Only the snapshot's
# own two fields are used for the gap; the history table is not. These numbers
# are synthetic, not company data.

E2E_TRADE_DATE = AS_OF          # the run's analysis date, reused from this file
E2E_TEXT = "Report.\n\n**Rating**: Overweight\n\nFINAL TRANSACTION PROPOSAL: **BUY**"

MARKET_TOOL = "get_verified_market_snapshot"
STATEMENT_TOOL = "get_income_statement"

STATEMENT_TEXT = (
    "# Synthetic income statement (USD in millions)\n"
    "Source: synthetic fixture; fiscal years ended 2025-05-31 and 2026-05-31\n"
    "\n"
    "Period,Cost of Revenue\n"
    "2025-05-31,100\n"
    "2026-05-31,125\n"
)

SNAPSHOT_FIELDS = ("Close", "boll_ub")
TOOL_ARGS = {
    "symbol": TICKER, "ticker": TICKER,
    "curr_date": E2E_TRADE_DATE, "start_date": "2025-05-31", "end_date": E2E_TRADE_DATE,
    "freq": "annual", "indicator": "boll",
}


def _synthetic_ohlcv():
    """A synthetic OHLCV series that rises and falls, ending on the run date."""
    import math

    import pandas as pd

    dates = pd.bdate_range(end=E2E_TRADE_DATE, periods=60)
    rows = []
    for index in range(60):
        close = 100.0 + index * 0.25 + 2.0 * math.sin(index / 3.0)
        rows.append({
            "Date": dates[index],
            "Open": round(close - 0.5, 4),
            "High": round(close + 1.0, 4),
            "Low": round(close - 1.0, 4),
            "Close": round(close, 4),
            "Volume": 1_000_000 + index,
        })
    return pd.DataFrame(rows)


class E2EScriptedModel(BaseChatModel):
    """Calls the two named tools once each, then answers with fixed text.

    ``tool_calls_made``, ``calls`` and ``received`` are shared across bound
    copies, so the test can show what really ran and which ToolMessages the
    bound models were given.
    """

    tools: tuple = ()
    calls: list = _PydanticField(default_factory=list)          # shared across copies
    tool_calls_made: list = _PydanticField(default_factory=list)  # shared across copies
    received: list = _PydanticField(default_factory=list)       # shared across copies

    @property
    def _llm_type(self) -> str:
        return "fr02-scripted"

    def bind_tools(self, tools, **kwargs):
        return self.model_copy(update={"tools": tuple(tools)})

    def with_structured_output(self, schema, **kwargs):
        from langchain_core.runnables import RunnableLambda

        from tradingagents.agents import schemas

        answers = {
            schemas.ResearchPlan: schemas.ResearchPlan(
                recommendation=schemas.PortfolioRating.OVERWEIGHT,
                rationale="r", strategic_actions="a"),
            schemas.TraderProposal: schemas.TraderProposal(
                action=schemas.TraderAction.BUY, reasoning="r"),
            schemas.PortfolioDecision: schemas.PortfolioDecision(
                rating=schemas.PortfolioRating.OVERWEIGHT,
                executive_summary="s",
                investment_thesis="Built on this run's verified metrics."),
            schemas.SentimentReport: schemas.SentimentReport(
                overall_band=schemas.SentimentBand.NEUTRAL,
                overall_score=5.0, confidence="low", narrative="n"),
        }
        return RunnableLambda(lambda _: self.calls.append(schema.__name__) or answers[schema])

    def _note_call(self):
        self.calls.append("structured")

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        from langchain_core.messages import AIMessage, ToolMessage
        from langchain_core.outputs import ChatGeneration, ChatResult

        self._note_call()
        for message in messages:
            if isinstance(message, ToolMessage):
                self.received.append(message)
        if self.tools and not isinstance(messages[-1], ToolMessage):
            bound = {tool.name: tool for tool in self.tools}
            wanted = [name for name in (MARKET_TOOL, STATEMENT_TOOL) if name in bound]
            calls = []
            for name in wanted:
                schema = bound[name].tool_call_schema.model_json_schema()["properties"]
                calls.append({
                    "name": name,
                    "id": f"call_{name}",
                    "args": {key: value for key, value in TOOL_ARGS.items() if key in schema},
                })
                self.tool_calls_made.append(name)
            if calls:
                return ChatResult(generations=[
                    ChatGeneration(message=AIMessage(content="", tool_calls=calls))])
        return ChatResult(generations=[
            ChatGeneration(message=AIMessage(content=E2E_TEXT))])


class _E2EClient:
    def __init__(self, model):
        self.model = model

    def get_llm(self):
        return self.model


def _e2e_offline_sources(monkeypatch):
    """Both data paths answered offline; returns the router methods called."""
    from tradingagents.agents import context
    from tradingagents.dataflows import router
    from tradingagents.dataflows.vendors.yahoo import market as yahoo_market, snapshot

    called: set = set()
    for method, vendors in router.VENDOR_METHODS.items():
        answer = STATEMENT_TEXT if method == STATEMENT_TOOL else f"{method} data"
        for vendor in vendors:
            monkeypatch.setitem(
                vendors, vendor,
                lambda *a, _method=method, _answer=answer, **k:
                    called.add(_method) or _answer,
            )
    prices = _synthetic_ohlcv()
    monkeypatch.setattr(snapshot, "load_ohlcv",
                        lambda *a, **k: called.add("ohlcv") or prices.copy())
    monkeypatch.setattr(
        yahoo_market.yf, "Ticker",
        lambda symbol: type("T", (), {"info": {"longName": TICKER}})(),
    )
    context._identity.cache_clear()
    return called


def _e2e_graph(tmp_path, monkeypatch, model):
    """A real graph whose providers, caches, reports and memory stay offline."""
    import copy

    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph import trading_graph

    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update(
        results_dir=str(tmp_path / "results"),
        data_cache_dir=str(tmp_path / "cache"),
        memory_log_path=str(tmp_path / "log.md"),
        checkpoint_enabled=False,
    )
    monkeypatch.setattr(trading_graph, "create_tier_client",
                        lambda cfg, tier, **k: _E2EClient(model))
    return trading_graph.TradingAgentsGraph(
        config=config, selected_analysts=("market", "fundamentals"))


def _two_column_rows(text, fields):
    """Field/value pairs from a two-column table, matched on the left cell only."""
    found = {}
    for line in str(text).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 2:
            continue
        name, value = cells
        if name in fields:
            found[name] = value
    return found


def _cost_of_revenue_by_period(text):
    """Cost of Revenue keyed by the period given on the reply's own column."""
    lines = [line for line in str(text).splitlines() if line.strip()]
    header_index = next(
        (i for i, line in enumerate(lines)
         if "Period" in line.split(",")[0] and "Cost of Revenue" in line),
        None,
    )
    assert header_index is not None, "the statement reply has no Period/Cost of Revenue header"
    header = [cell.strip() for cell in lines[header_index].split(",")]
    period_column = header.index("Period")
    value_column = header.index("Cost of Revenue")
    rows = {}
    for line in lines[header_index + 1:]:
        if line.lstrip().startswith("#"):
            break
        cells = [cell.strip() for cell in line.split(",")]
        if len(cells) <= max(period_column, value_column):
            continue
        period, value = cells[period_column], cells[value_column]
        if period and value:
            rows[period] = value
    return rows


def _finte_decimal(text):
    """The value as a finite Decimal, or a clear failure."""
    value = Decimal(str(text).replace("$", "").replace(",", "").strip())
    assert value.is_finite(), f"{text!r} is not a finite number"
    return value


def _metric_records(state):
    registry = state.get("verified_metrics") or {}
    return list(registry.values()) if isinstance(registry, dict) else list(registry)


def _records_for(state, run, kind):
    """Verified records of one kind for the run passed in, by its own identity."""
    return [
        record for record in _metric_records(state)
        if record.get("kind") == kind
        and record.get("run_id") == run.get("run_id")
        and record.get("ticker") == run.get("ticker")
        and record.get("as_of_date") == run.get("as_of_date")
    ]


@pytest.mark.parametrize("max_tool_rounds", [None, 1], ids=["default", "one-round"])
def test_fr02_e2e_fake_model_real_graph(tmp_path, monkeypatch, caplog,
                                        max_tool_rounds):
    """FR-02 normal path: both analyst inputs reach the run's verified metrics.

    Expected failure on the unmodified baseline: the assertion that the parent
    state carries verified metrics (step 5) fails, after the positive controls
    in steps 1-4 have passed. It is not an import error, a collected-nothing
    run, or a broken graph.

    This case uses its own sources, which carry complete metadata at the vendor
    layer. The statement path is the real SEC implementation, answered only at
    ``_fetch_json``; the price path keeps the real ``load_ohlcv`` and
    ``snapshot``, answered by a simulated Yahoo ticker whose metadata is only
    reachable after ``history`` has been called. Nothing writes a currency into
    a price table, a tool reply, the state or the report: whether the product
    reads the vendor's currency is what this case is here to show.
    """
    from langchain_core.messages import ToolMessage

    def _e2e_full_metadata_sources(monkeypatch):
        """Offline vendors with complete metadata; returns what was actually read.

        The log records ``STATEMENT_TOOL`` only when the SEC document carrying
        the two facts is really served, and ``"ohlcv"`` only when the price
        series is really requested. Each simulated ticker keeps its own record,
        and one that never served history offers no metadata at all.
        """
        from tradingagents.agents import context
        from tradingagents.dataflows import router
        from tradingagents.dataflows.vendors import sec_edgar
        from tradingagents.dataflows.vendors.yahoo import market as yahoo_market

        log: list = []
        cik = "0000000001"
        facts_url = sec_edgar._FACTS_URL.format(cik=cik)

        def fact(start, end, value, accession, fiscal_year):
            return {"start": start, "end": end, "val": value, "accn": accession,
                    "fy": fiscal_year, "fp": "FY", "form": "10-K",
                    "filed": end.replace("-05-31", "-08-15"), "frame": None}

        companyfacts = {
            "cik": int(cik),
            "entityName": TICKER,
            "facts": {"us-gaap": {"CostOfRevenue": {"label": "Cost of Revenue", "units": {
                "USD": [
                    fact("2024-06-01", "2025-05-31", 100000000, "0000000001-25-000001", 2025),
                    fact("2025-06-01", "2026-05-31", 125000000, "0000000001-26-000001", 2026),
                ]}}}},
        }

        def fetch_json(url):
            if url == sec_edgar._TICKERS_URL:
                return {"0": {"cik_str": int(cik), "ticker": TICKER, "title": TICKER}}
            if url == facts_url:
                log.append(STATEMENT_TOOL)
                return companyfacts
            raise AssertionError(f"unexpected SEC URL {url}")

        class _Ticker:
            """A simulated ticker: history first, metadata only afterwards."""

            def __init__(self, symbol):
                self.symbol = symbol
                self.info = {"longName": TICKER}
                self.history_called = False
                self.metadata_read = False

            def history(self, start=None, end=None, auto_adjust=True, actions=False):
                self.history_called = True
                log.append("ohlcv")
                return series.copy()

            def get_history_metadata(self):
                if not self.history_called:
                    raise AssertionError("metadata was read before history")
                self.metadata_read = True
                log.append("get_history_metadata")
                return {"symbol": self.symbol, "currency": "USD"}

        tickers = []

        def make_ticker(symbol):
            ticker = _Ticker(symbol)
            tickers.append(ticker)
            return ticker

        def offline_only(*args, **kwargs):
            raise AssertionError("an offline stub reached the network path")

        for method, vendors in router.VENDOR_METHODS.items():
            for vendor in vendors:
                if method == STATEMENT_TOOL:
                    # Only the real SEC implementation may answer the statement;
                    # any other configured vendor must never be reached.
                    monkeypatch.setitem(
                        vendors, vendor,
                        sec_edgar.get_income_statement if vendor == "sec_edgar"
                        else offline_only,
                    )
                    continue
                monkeypatch.setitem(
                    vendors, vendor,
                    lambda *a, _method=method, **k: log.append(_method) or f"{_method} data",
                )
        monkeypatch.setattr(sec_edgar, "_fetch_json", fetch_json)
        series = _synthetic_ohlcv().set_index("Date")
        monkeypatch.setattr(yahoo_market.yf, "Ticker", make_ticker)
        context._identity.cache_clear()
        return log, tickers

    called, tickers = _e2e_full_metadata_sources(monkeypatch)
    model = E2EScriptedModel()
    watcher = None
    if max_tool_rounds is not None:
        import logging

        from langchain_core.callbacks import BaseCallbackHandler
        from langchain_core.messages import ToolMessage

        from tradingagents import default_config as _default_config

        class _ToolReplyWatcher(BaseCallbackHandler):
            """Keeps the real ToolMessages the executed tool nodes returned.

            The wrap-up turn hands the model only converted text, so the reply
            of each tool this run really called is read here, off the graph
            that actually runs. Nothing is written into the state.
            """

            def __init__(self):
                super().__init__()
                self.messages: list = []
                self.errors: list = []

            def on_tool_end(self, output, **kwargs):
                if isinstance(output, ToolMessage):
                    self.messages.append(output)

            def on_tool_error(self, error, **kwargs):
                self.errors.append(error)

        watcher = _ToolReplyWatcher()
        caplog.set_level(logging.WARNING)
        # The graph reads max_tool_rounds from the default configuration when
        # it is built, so the default is changed only for that build.
        monkeypatch.setitem(_default_config.DEFAULT_CONFIG, "max_tool_rounds",
                            max_tool_rounds)
    graph = _e2e_graph(tmp_path, monkeypatch, model)
    if watcher is not None:
        graph.graph = graph.graph.with_config(callbacks=[watcher])

    state, signal = graph.propagate(TICKER, E2E_TRADE_DATE)

    # The vendor handed over the currency; the product had to ask for it. Only
    # asserted once this run issued a metric, so the baseline still fails on the
    # verified-metrics assertion below instead of here.
    if state.get("verified_metrics"):
        asked = [t for t in tickers if t.symbol == TICKER]
        assert asked, "the run never asked the simulated supplier for SYN"
        assert any(t.history_called and t.metadata_read for t in asked), (
            "no simulated SYN ticker both served history and had its metadata read")

    # Re-read the run's verified metrics through the product's own resolver
    # before anything is saved. Resolution needs the run's course_run and the
    # caller's registry; while either is absent these stay None so the
    # baseline still fails at step 6, where it always failed.
    _course_run = state.get("course_run")
    _registry = state.get("verified_metrics")
    trusted = {}
    if isinstance(_course_run, dict) and _registry:
        from tradingagents.agents import verified_metrics as _vt

        for _record in _metric_records(state):
            _metric_id = _record.get("metric_id")
            if not _metric_id:
                continue
            trusted[_metric_id] = _vt.resolve_metric(_metric_id, _registry, _course_run)

    report_path = graph.save_reports(state, TICKER, tmp_path / "report", html=False)
    report_text = report_path.read_text(encoding="utf-8")

    # 1. This run really called both tools, once each.
    assert model.tool_calls_made.count(MARKET_TOOL) == 1, (
        f"expected one {MARKET_TOOL} call, saw {model.tool_calls_made}")
    assert model.tool_calls_made.count(STATEMENT_TOOL) == 1, (
        f"expected one {STATEMENT_TOOL} call, saw {model.tool_calls_made}")

    # 2. Both tools returned a real, non-error ToolMessage.
    if max_tool_rounds is None:
        by_name = {}
        for message in model.received:
            by_name.setdefault(message.name, []).append(message)
    else:
        # Both analysts used their single round and were told to file their
        # report: exactly one such warning per analyst, from the module that
        # writes it. The replies are read from this run's own tool callbacks.
        for node in ("Market Analyst", "Fundamentals Analyst"):
            warnings = [
                record for record in caplog.records
                if node in record.getMessage()
                and "asking for its report" in record.getMessage()
                and record.name == "tradingagents.graph.setup"
                and record.levelno >= logging.WARNING
            ]
            assert len(warnings) == 1, (
                f"{node} filed {len(warnings)} one-round wrap-up warnings; seen: "
                f"{[r.getMessage() for r in caplog.records if node in r.getMessage()]}")
            assert "its 1 tool rounds" in warnings[0].getMessage(), (
                f"the {node} warning is not a one-round wrap-up: "
                f"{warnings[0].getMessage()!r}")
        assert not watcher.errors, f"a tool failed this run: {watcher.errors}"
        by_name = {}
        for message in watcher.messages:
            by_name.setdefault(message.name, []).append(message)
        for name in (MARKET_TOOL, STATEMENT_TOOL):
            assert name in by_name, f"the executed tool nodes returned no {name} message"
            replies = by_name[name]
            assert len(replies) == 1, (
                f"expected one {name} reply this run, saw {len(replies)}")
            assert replies[0].tool_call_id == f"call_{name}", (
                f"the {name} reply carries another call ID: {replies[0].tool_call_id!r}")
            assert getattr(replies[0], "status", "success") != "error", (
                f"the {name} reply is an error message")
    assert MARKET_TOOL in by_name, f"{MARKET_TOOL} returned no ToolMessage"
    assert STATEMENT_TOOL in by_name, f"{STATEMENT_TOOL} returned no ToolMessage"
    snapshot_message = by_name[MARKET_TOOL][-1]
    statement_message = by_name[STATEMENT_TOOL][-1]
    assert isinstance(snapshot_message, ToolMessage)
    assert isinstance(statement_message, ToolMessage)
    assert getattr(snapshot_message, "status", "success") != "error", (
        "the snapshot tool result is an error message")
    assert getattr(statement_message, "status", "success") != "error", (
        "the statement tool result is an error message")

    # 3. The statement reply's own two rows, checked on their own periods.
    by_period = _cost_of_revenue_by_period(statement_message.content)
    assert by_period.get("2025-05-31") == "100", f"prior row is {by_period!r}"
    assert by_period.get("2026-05-31") == "125", f"current row is {by_period!r}"
    prior_value = _finte_decimal(by_period["2025-05-31"])
    current_value = _finte_decimal(by_period["2026-05-31"])

    # 4. The snapshot reply's own two finite fields, before the state is read.
    snapshot = _two_column_rows(snapshot_message.content, SNAPSHOT_FIELDS)
    assert set(snapshot) == set(SNAPSHOT_FIELDS), (
        f"the snapshot table lacks {sorted(set(SNAPSHOT_FIELDS) - set(snapshot))}")
    close_value = _finte_decimal(snapshot["Close"])
    upper_band = _finte_decimal(snapshot["boll_ub"])

    # 5. The analysts, the decision and the saved report all have content.
    assert "ohlcv" in called, "the snapshot path read no prices"
    assert STATEMENT_TOOL in called, "the statement path was not called"
    assert state.get("market_report", "").strip(), "the market analyst filed no report"
    assert state.get("fundamentals_report", "").strip(), "the fundamentals analyst filed no report"
    assert "PortfolioDecision" in model.calls
    assert state["publication_status"] == "BLOCKED"
    assert state["publication_reason"] == "INSUFFICIENT_EVIDENCE"
    assert not state["final_trade_decision"]
    assert report_text.strip(), "the saved report is empty"

    # 6. The parent state carries verified metrics from both inputs.
    #    Expected failure on the unmodified baseline: this assertion.
    assert state.get("verified_metrics"), (
        "the run carries no verified metrics from either analyst input")

    # 7. The run identity comes from the graph's own course_run, not the records.
    course_run = state.get("course_run")
    assert course_run, "the run carries no course_run"
    run_id = course_run["run_id"]
    ticker = course_run["ticker"]
    as_of = course_run["as_of_date"]
    assert run_id and ticker and as_of
    assert ticker == TICKER, "course_run names another ticker than this run"
    assert as_of == E2E_TRADE_DATE, "course_run carries another date than this run"

    # 8. Records for this run, ticker, date and input; each kind may have several.
    yoy_records = _records_for(state, course_run, "yoy")
    delta_records = _records_for(state, course_run, "price_delta")
    assert yoy_records, "no verified YoY record for this run from the statement input"
    assert delta_records, "no verified price gap for this run from the snapshot input"

    # 9. The YoY carries the statement reply's own roles, values and fiscal ends.
    expected_yoy = Decimal(100) * (current_value / prior_value - 1)
    matching_yoy = [
        record for record in yoy_records
        if abs(_finte_decimal(record["result_value"]) - expected_yoy) <= PERCENT_TOLERANCE
        and _operand_matches(record, [
            ("prior", prior_value, "Cost of Revenue", "2025-05-31"),
            ("current", current_value, "Cost of Revenue", "2026-05-31"),
        ])
    ]
    assert matching_yoy, (
        "no YoY record matches the statement's prior/current operands by value and fiscal end")
    yoy = matching_yoy[0]
    assert yoy.get("result_unit") == "%"

    # 10. The price gap carries boll_ub as current and Close as reference.
    #     The expectation is recomputed here from this test's own synthetic
    #     series, and the reply's # FR02_QUOTE_SOURCE line supplies the raw
    #     values the record must carry. The record is never its own expectation.
    import json
    import statistics

    source_lines = [line for line in snapshot_message.content.splitlines() if line.strip()]
    assert source_lines[-1].startswith("# FR02_QUOTE_SOURCE "), (
        "the snapshot reply's last line is not the quote source")
    quote = json.loads(source_lines[-1][len("# FR02_QUOTE_SOURCE "):], parse_float=Decimal)
    assert isinstance(quote, dict), "the quote source is not a JSON object"

    closes = [Decimal(str(value)) for value in _synthetic_ohlcv()["Close"].tolist()]
    synthetic_close = closes[-1]
    window = closes[-20:]
    synthetic_upper = statistics.mean(window) + 2 * statistics.stdev(window)

    assert quote.get("symbol") == TICKER, "the quote source names another stock"
    assert quote.get("currency") == "USD", "the quote source states another currency"
    assert quote.get("as_of_date") == E2E_TRADE_DATE, (
        "the quote source states another request date")
    assert quote.get("trading_date") == E2E_TRADE_DATE, (
        "the quote source states another trading day")

    close_from_source = _finte_decimal(quote.get("close"))
    upper_from_source = _finte_decimal(quote.get("boll_ub"))
    assert close_from_source == synthetic_close, (
        f"the source close {quote.get('close')} is not this series' last close {synthetic_close}")
    assert abs(upper_from_source - synthetic_upper) <= Decimal("1e-9"), (
        f"the source upper band {upper_from_source} is not the 20-day mean plus two "
        f"sample standard deviations ({synthetic_upper})")

    # The displayed table shows the same two prices at the snapshot's own
    # precision: six significant figures, at least two decimals. The precision
    # is taken from the raw figure, never read back from what is displayed.
    for shown, raw in ((close_value, close_from_source), (upper_band, upper_from_source)):
        decimals = 2 if raw == 0 else max(2, 5 - abs(raw).adjusted())
        assert shown == raw.quantize(Decimal(1).scaleb(-decimals)), (
            f"the displayed {shown} is not {raw} at its own precision")

    expected_gap = upper_from_source - close_from_source
    matching_delta = [
        record for record in delta_records
        if abs(_finte_decimal(record["result_value"]) - expected_gap) <= PRICE_TOLERANCE
        and _operand_matches(record, [
            ("current", upper_from_source, "boll_ub", quote.get("trading_date")),
            ("reference", close_from_source, "Close", quote.get("trading_date")),
        ])
    ]
    assert matching_delta, (
        "no price gap record matches the source's boll_ub - Close by role, value and quote date")
    delta = matching_delta[0]
    assert delta.get("result_unit") == "USD"

    # 11. Sources are recorded and reachable for both records. The source string
    #     format is the product's; this checks presence and correspondence only.
    for record, label in ((yoy, "YoY"), (delta, "price gap")):
        assert _linkable(record, state.get("course_run")) is not None, (
            f"the {label} record keeps no reachable source")

    # 12. Both records must have been re-read through resolve_metric before the
    #     report was saved. Taken after the baseline's own failure point, so the
    #     unmodified baseline still fails at step 6 on verified_metrics.
    for record, label in ((yoy, "YoY"), (delta, "price gap")):
        resolved = trusted.get(record["metric_id"])
        assert resolved is not None, (
            f"resolve_metric did not re-read the {label} record {record['metric_id']}")
        assert resolved.get("metric_id") == record["metric_id"], (
            f"resolve_metric returned another record for the {label} ID")
        assert _linkable(resolved, None) is not None, (
            f"the resolved {label} record lost its source")

    # 13. The Portfolio Manager's structured list carries each record by ID.
    listed = state.get("portfolio_verified_metrics")
    assert isinstance(listed, list) and listed, (
        "the Portfolio Manager filed no portfolio_verified_metrics list")
    for record, label in ((yoy, "YoY"), (delta, "price gap")):
        resolved = trusted[record["metric_id"]]
        entry = _pm_entry(listed, record["metric_id"])
        assert entry is not None, (
            f"the Portfolio Manager list holds no {label} record {record['metric_id']}")
        assert entry.get("result_unit") == resolved.get("result_unit"), (
            f"the Portfolio Manager {label} unit differs from the trusted record")
        assert _same_number(entry.get("result_value"), resolved.get("result_value")), (
            f"the Portfolio Manager {label} value differs from the trusted record")

    # 14. The saved report's ## Verified Metrics table carries each record by ID.
    table = _verified_metrics_table(report_text)
    assert table, "the saved report has no ## Verified Metrics table"
    for record, label in ((yoy, "YoY"), (delta, "price gap")):
        resolved = trusted[record["metric_id"]]
        row = _table_row(table, record["metric_id"])
        assert row is not None, (
            f"the report's Verified Metrics table holds no {label} row "
            f"for {record['metric_id']}")
        assert row["unit"] == resolved.get("result_unit"), (
            f"the report {label} unit differs from the trusted record")
        tolerance = (PERCENT_TOLERANCE if resolved.get("result_unit") == "%"
                     else PRICE_TOLERANCE)
        assert abs(_finte_decimal(row["value"])
                   - _finte_decimal(resolved["result_value"])) <= tolerance, (
            f"the report {label} cell {row['value']!r} differs from the trusted "
            f"record by more than {tolerance}")


def _pm_entry(listed, metric_id):
    """The single Portfolio Manager entry for this ID, or None."""
    matches = [entry for entry in listed
               if isinstance(entry, dict) and entry.get("metric_id") == metric_id]
    return matches[0] if len(matches) == 1 else None


def _same_number(left, right):
    """Equal by numbering: "25", "25.0" and "2.5E1" are the same value."""
    try:
        return _finte_decimal(left) == _finte_decimal(right)
    except (AssertionError, ValueError):
        return False


def _verified_metrics_table(report_text):
    """Body rows of the ## Verified Metrics table in the report, or None.

    Parsed with markdown-it-py, so only a real Markdown table counts. The
    section starts at the level-2 heading ``Verified Metrics`` and ends at the
    next heading of that level or higher; a fenced block is a single node and
    is skipped as such, so ordinary headings after it are still read. The
    table's header must be exactly ``metric_id``, ``value``, ``unit`` and only
    its body rows are returned. A lookalike table elsewhere, or the same number
    in body prose, does not qualify.
    """
    from markdown_it import MarkdownIt
    from markdown_it.tree import SyntaxTreeNode

    document = SyntaxTreeNode(MarkdownIt("commonmark").enable("table").parse(str(report_text)))
    children = list(document.children)

    def heading(node):
        text = "".join(child.content for child in node.children).strip()
        return text, int(node.tag.lstrip("h"))

    for index, node in enumerate(children):
        if node.type != "heading" or heading(node) != ("Verified Metrics", 2):
            continue
        level = 2
        for candidate in children[index + 1:]:
            if candidate.type == "heading":
                text, candidate_level = heading(candidate)
                if candidate_level <= level:
                    break
            if candidate.type != "table":
                continue
            head, body = candidate.children
            header = [cell.children[0].content.strip() for cell in head.children[0].children]
            if header != ["metric_id", "value", "unit"]:
                continue
            rows = []
            for row in body.children:
                cells = [cell.children[0].content.strip() for cell in row.children]
                if len(cells) == len(header):
                    rows.append(dict(zip(header, cells, strict=True)))
            return rows or None
    return None


def _table_row(table, metric_id):
    """The single table row for this ID, or None."""
    matches = [row for row in table if row.get("metric_id") == metric_id]
    return matches[0] if len(matches) == 1 else None


def _linkable(record, course_run):
    """A nonempty provenance: recorded sources, and at least one operand citing one.

    ``VerifiedMetric.source_refs`` holds the record's inputs; each operand's own
    ``source_ref`` names the source it came from. The string spelling is the
    product's, so only presence and correspondence are required.
    """
    sources = [source for source in (record.get("source_refs") or []) if source]
    if not sources:
        return None
    cited = {operand.get("source_ref") for operand in (record.get("operands") or [])
             if operand.get("source_ref")}
    if not cited:
        return None
    if not cited & set(sources):
        return None
    return sources


def _operand_matches(record, expected_operands):
    """Every expected role's operand carries the reply's own value, field and end.

    Each expected item is ``(role, value, field_ref, period_end)``. The operand
    for that role must exist, hold that finite value, name that field and end on
    that date; its own ``source_ref`` must appear in the record's
    ``source_refs``. Source strings are the product's, so only membership is
    required. Uses ``_finte_decimal`` and nothing else.
    """
    sources = record.get("source_refs") or []
    recorded = set(sources)
    operands = record.get("operands") or []
    for role, value, field_ref, period_end in expected_operands:
        operand = next(
            (candidate for candidate in operands if candidate.get("role") == role), None)
        if operand is None:
            return False
        if _finte_decimal(operand.get("value")) != value:
            return False
        if operand.get("field_ref") != field_ref:
            return False
        if (operand.get("period") or {}).get("end") != period_end:
            return False
        if operand.get("source_ref") not in recorded:
            return False
    return True


# --- T-FR02-IDENTITY at the consumer end --------------------------------
# The real verify_metric signs records; the real Portfolio Manager node and
# write_report_tree consume them. Each case is its own run, so one case can
# never resolve another's IDs. No whole-graph run and no network.
#
# The structured group uses the fixed model this file already has, which
# answers with a real PortfolioDecision. The plain group refuses
# with_structured_output, so the manager takes its free-text path exactly as
# it would with a provider that cannot bind; the text model's own call log
# shows which path ran.

PM_KEYS = ("risk_debate_state", "candidate_decision", "candidate_rating",
           "portfolio_verified_metrics")


class _PMTextOnlyModel:
    """A plain chat model: no structured output, fixed free text, logged calls."""

    def __init__(self):
        self.prompts = []

    def _llm_type(self):
        return "fr02-consumer-text"

    def with_structured_output(self, schema, **kwargs):
        raise NotImplementedError("this profile has no structured output")

    def invoke(self, prompt, **kwargs):
        from langchain_core.messages import AIMessage

        self.prompts.append(prompt)
        return AIMessage(content=E2E_TEXT)


def _pm_state(course_run, registry, ticker, as_of):
    """The state keys the Portfolio Manager reads, plus this run's metrics."""
    return {
        "messages": [],
        "company_of_interest": ticker,
        "asset_type": "stock",
        "instrument_context": "",
        "trade_date": as_of,
        "past_context": "",
        "portfolio_context": "",
        "risk_debate_state": {
            "history": "Aggressive and Conservative argued; the evidence held.",
            "aggressive_history": "a",
            "conservative_history": "c",
            "neutral_history": "n",
            "latest_speaker": "Neutral Analyst",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 3,
        },
        "investment_plan": "Hold and watch the band.",
        "trader_investment_plan": "Buy a partial position.",
        "memory_note": "",
        "course_run": course_run,
        "verified_metrics": registry,
    }


def _sign(run, kind="price_delta", current="10.125", reference="5.599"):
    """Sign one record with the real verify_metric; return (metric_id, record)."""
    from tradingagents.agents import verified_metrics

    request = _delta(current, reference) if kind == "price_delta" else _yoy(current, reference)
    result = verified_metrics.verify_metric(request, run)
    metric = _verified(result)
    return metric["metric_id"], metric


def _pm_update(state):
    """The real Portfolio Manager node's return value on the free-text path."""
    from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

    model = _PMTextOnlyModel()
    update = create_portfolio_manager(model)(state)
    assert model.prompts, "the free-text path was never taken"
    return update


def _report_with(state, ticker, tmp_path, name, candidates):
    """Write the real report with the given candidates; return its text.

    The state keeps its registry and run untouched, so the report itself
    decides which candidate IDs it may show.
    """
    from tradingagents.reporting import write_report_tree

    saved = dict(state)
    saved["portfolio_verified_metrics"] = candidates
    path = write_report_tree(saved, ticker, tmp_path / name, settings=None, html=False)
    return path.read_text(encoding="utf-8")


def test_fr02_consumer_verified_record_reaches_manager_and_report(tmp_path):
    """One signed record, checked once in the manager list and once in the report."""
    run = _run("run-fr02-consumer-0001")
    metric_id, record = _sign(run)
    state = _pm_state(run, {metric_id: record}, TICKER, AS_OF)

    update = _pm_update(state)
    assert update["portfolio_verified_metrics"] == [
        {"metric_id": metric_id,
         "result_value": record["result_value"],
         "result_unit": record["result_unit"]}], "the manager list lost the signed record"

    text = _report_with(state, TICKER, tmp_path, "signed", update["portfolio_verified_metrics"])
    row = _table_row(_verified_metrics_table(text), metric_id)
    assert row is not None, "the report has no row for the signed metric"
    assert row["metric_id"] == metric_id
    assert row["value"] == record["result_value"]
    assert row["unit"] == record["result_unit"]


def test_fr02_consumer_altered_value_is_not_shown(tmp_path):
    """The real ID with a changed value: the manager refuses, then the report does."""
    run = _run("run-fr02-consumer-0002")
    metric_id, record = _sign(run)
    altered = dict(record)
    altered["result_value"] = "999"
    state = _pm_state(run, {metric_id: altered}, TICKER, AS_OF)

    update = _pm_update(state)
    assert update["portfolio_verified_metrics"] == [], (
        "an altered record reached the manager list")

    text = _report_with(state, TICKER, tmp_path, "altered", [{"metric_id": metric_id}])
    assert _verified_metrics_table(text) is None, "an altered record reached the report"


def test_fr02_consumer_altered_source_is_not_shown(tmp_path):
    """The real ID with a changed source: the manager refuses, then the report does."""
    run = _run("run-fr02-consumer-0003")
    metric_id, record = _sign(run)
    altered = {key: (list(value) if isinstance(value, list) else value)
               for key, value in record.items()}
    altered["source_refs"] = ["fixture:not-the-verified-source"]
    state = _pm_state(run, {metric_id: altered}, TICKER, AS_OF)

    update = _pm_update(state)
    assert update["portfolio_verified_metrics"] == [], (
        "a record with an altered source reached the manager list")

    text = _report_with(state, TICKER, tmp_path, "altered-source", [{"metric_id": metric_id}])
    assert _verified_metrics_table(text) is None, "a record with an altered source was shown"


def test_fr02_consumer_forged_id_is_not_shown(tmp_path):
    """An ID this run never issued: refused by the manager and by the report."""
    run = _run("run-fr02-consumer-0004")
    _, record = _sign(run)
    forged = dict(record)
    forged["metric_id"] = "metric-self-declared"
    state = _pm_state(run, {forged["metric_id"]: forged}, TICKER, AS_OF)

    update = _pm_update(state)
    assert update["portfolio_verified_metrics"] == [], "a forged ID reached the manager list"

    text = _report_with(state, TICKER, tmp_path, "forged",
                        [{"metric_id": "metric-self-declared"}])
    assert _verified_metrics_table(text) is None, "a forged ID reached the report"


def test_fr02_consumer_prior_run_record_is_not_shown(tmp_path):
    """A record signed for another run, offered to this one: refused in both places."""
    other = _run("run-fr02-consumer-0005-out")
    metric_id, record = _sign(other)
    run = _run("run-fr02-consumer-0005")
    state = _pm_state(run, {metric_id: record}, TICKER, AS_OF)

    update = _pm_update(state)
    assert update["portfolio_verified_metrics"] == [], (
        "another run's record reached the manager list")

    text = _report_with(state, TICKER, tmp_path, "prior-run", [{"metric_id": metric_id}])
    assert _verified_metrics_table(text) is None, "another run's record reached the report"


def test_fr02_consumer_candidates_are_filtered_and_deduplicated(tmp_path):
    """Fake numbers, repeated IDs and non-string IDs never displace the real row."""
    run = _run("run-fr02-consumer-0006")
    metric_id, record = _sign(run)
    yoy_id, yoy_record = _sign(run, kind="yoy", current="125", reference="100")
    state = _pm_state(run, {metric_id: record, yoy_id: yoy_record}, TICKER, AS_OF)

    update = _pm_update(state)
    listed = update["portfolio_verified_metrics"]
    assert {entry["metric_id"] for entry in listed} == {metric_id, yoy_id}

    text = _report_with(state, TICKER, tmp_path, "candidates", [
        {"metric_id": metric_id, "result_value": "999", "result_unit": "USD"},
        {"metric_id": metric_id, "result_value": "888", "result_unit": "USD"},
        {"metric_id": yoy_id, "result_value": "777", "result_unit": "%"},
        {"metric_id": ["not", "a", "string"], "result_value": "1", "result_unit": "USD"},
        {"metric_id": {"nested": "id"}, "result_value": "1", "result_unit": "USD"},
        {"metric_id": "metric-never-issued", "result_value": "1", "result_unit": "USD"},
    ])
    table = _verified_metrics_table(text)
    assert table is not None, "the report dropped every trustworthy row"
    ids = [row["metric_id"] for row in table]
    assert ids == [metric_id, yoy_id], f"unexpected rows: {ids}"
    assert table[0]["value"] == record["result_value"], "the fake number was used"
    assert table[0]["unit"] == record["result_unit"]
    assert table[1]["value"] == yoy_record["result_value"]
    assert table[1]["unit"] == yoy_record["result_unit"]


def test_fr02_consumer_structured_and_text_paths_agree(tmp_path):
    """Both decision paths keep the manager's keys and the same verified list."""
    from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

    run = _run("run-fr02-consumer-0007")
    metric_id, record = _sign(run)
    state = _pm_state(run, {metric_id: record}, TICKER, AS_OF)

    structured_model = E2EScriptedModel()
    typed_update = create_portfolio_manager(structured_model)(state)
    assert structured_model.calls, "the structured path was never taken"

    text_update = _pm_update(state)

    for update in (typed_update, text_update):
        for key in PM_KEYS:
            assert key in update, f"the Portfolio Manager lost its {key}"
        assert "final_rating" not in update and "final_trade_decision" not in update
        assert update["portfolio_verified_metrics"] == [
            {"metric_id": metric_id,
             "result_value": record["result_value"],
             "result_unit": record["result_unit"]}]
    assert typed_update["candidate_rating"] == text_update["candidate_rating"]
    assert typed_update["candidate_decision"] != text_update["candidate_decision"]


def test_fr02_consumer_legacy_state_without_course_run(tmp_path):
    """A state with the manager's keys but no course_run or registry still works."""
    run = _run("run-fr02-consumer-0008")
    state = _pm_state(run, {}, TICKER, AS_OF)
    state.pop("course_run")
    state.pop("verified_metrics")

    update = _pm_update(state)
    for key in PM_KEYS:
        assert key in update, f"the Portfolio Manager lost its {key}"
    assert update["portfolio_verified_metrics"] == []

    state.update(update)
    from tradingagents.reporting import write_report_tree

    path = write_report_tree(state, TICKER, tmp_path / "legacy", settings=None, html=False)
    text = path.read_text(encoding="utf-8")
    assert "## Verified Metrics" not in text, "the legacy state gained a metrics section"
    assert text.strip(), "the legacy report is empty"


# --- T-FR02-YOY / RATIO / DELTA on frozen company operands ---------------
# Sample revision: FR02-FIX-02. Base: the FR-02 requirement rows and the D4
# AAPL acceptance examples.
#
# Every operand below is transcribed into this file, so the cases run from
# embedded data and need nothing from any archive on a developer's machine.
# Where the original material lives is recorded here so a later reviewer can
# locate it again:
#
# * NVDA: Revenues, fiscal 2027 Q2 against fiscal 2026 Q2, from the retained
#   SEC 10-Q 0001045810-26-000075, whose reporting period is Q2. The tool reply
#   from that run was not kept, so only the statement figures are embedded.
#   Statement amounts are USD millions, which is the unit recorded on each
#   operand.
# * AAPL: Cost of Revenue, fiscal 2026 against fiscal 2025, from the annual
#   income statement (lines 23-24) and SEC 10-K 0000320193-26-000026, field
#   CostOfGoodsAndServicesSold. Amounts are USD millions.
# * MSFT: capital expenditure over operating cash flow, fiscal 2026, from the
#   annual cash-flow statement (line 23) and SEC 10-K 0001193125-26-323660,
#   fields PaymentsToAcquirePropertyPlantAndEquipment and
#   NetCashProvidedByUsedInOperatingActivities. Amounts are USD millions; the
#   numerator keeps its positive sign as the statement reports it.
# * AAPL snapshot 2026-11-10: boll_ub and Close from that day's retained
#   snapshot. USD is this sample's agreed quote unit (D4 / SRC-07).
#
# These are not the synthetic controls above: each carries its own units and
# its own source reference, never the SYN fixture.

FROZEN_RUN_PREFIX = "run-fr02-frozen-"
FROZEN_TICKERS = {"NVDA": "NVDA", "AAPL": "AAPL", "MSFT": "MSFT"}


def _frozen_run(ticker, suffix):
    """A C0 RunContext for one frozen case: its own ticker and its own run_id."""
    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": f"{FROZEN_RUN_PREFIX}{suffix}",
        "ticker": FROZEN_TICKERS[ticker],
        "as_of_date": AS_OF,
        "execution_status": "RUNNING",
        "request_limit": 40,
    }


def _frozen_period(kind, start, end, label):
    return {"kind": kind, "start": start, "end": end, "label": label}


def _frozen_operand(role, value, unit, period, source_ref, field_ref):
    """One operand of a frozen case, with that case's own source and units."""
    return {
        "role": role,
        "value": value,
        "unit": unit,
        "period": dict(period),
        "source_ref": source_ref,
        "field_ref": field_ref,
    }


def _frozen_check(metric, request, expected_value, tolerance, run):
    """VERIFIED, the expected value, the unit, and each operand as it was given."""
    value = _value(metric)
    assert abs(value - expected_value) <= tolerance, (
        f"{value} differs from the independent value {expected_value} "
        f"by more than {tolerance}")
    _assert_provenance(metric, run, request)
    for expected in request["operands"]:
        actual = next(o for o in metric["operands"] if o["role"] == expected["role"])
        assert actual["period"] == expected["period"], (
            f"{expected['role']} period altered")
        assert actual["field_ref"] == expected["field_ref"], (
            f"{expected['role']} field altered")
    return value


def test_fr02_frozen_nvda_revenues_yoy():
    """T-FR02-YOY: NVDA Revenues, FY2027 Q2 against FY2026 Q2, displays 105.85%."""
    run = _frozen_run("NVDA", "nvda-yoy")
    source = "sec:10-Q:0001045810-26-000075:Revenues"
    prior = _frozen_period("quarter", "2025-04-28", "2025-07-27", "FY2026 Q2")
    current = _frozen_period("quarter", "2026-04-27", "2026-07-26", "FY2027 Q2")
    request = _request("yoy", [
        _frozen_operand("current", "96221", "USD_millions", current, source, "Revenues"),
        _frozen_operand("prior", "46743", "USD_millions", prior, source, "Revenues"),
    ])

    metric = _verified(_owner().verify_metric(request, run))
    expected = Decimal(100) * (Decimal(96221) / Decimal(46743) - 1)
    _frozen_check(metric, request, expected, PERCENT_TOLERANCE, run)
    assert metric["result_unit"] == "%"
    assert set(metric["source_refs"]) == {source}
    assert expected.quantize(Decimal("0.01")) == Decimal("105.85")


def test_fr02_frozen_aapl_cost_of_revenue_yoy():
    """T-FR02-YOY: AAPL Cost of Revenue, FY2026 against FY2025, displays 10.98%."""
    run = _frozen_run("AAPL", "aapl-yoy")
    source = "sec:10-K:0000320193-26-000026:CostOfGoodsAndServicesSold"
    prior = _frozen_period("year", "2024-09-29", "2025-09-27", "FY2025")
    current = _frozen_period("year", "2025-09-28", "2026-09-26", "FY2026")
    request = _request("yoy", [
        _frozen_operand("current", "245232", "USD_millions", current, source,
                        "Cost of Revenue"),
        _frozen_operand("prior", "220960", "USD_millions", prior, source,
                        "Cost of Revenue"),
    ])

    metric = _verified(_owner().verify_metric(request, run))
    expected = Decimal(100) * (Decimal(245232) / Decimal(220960) - 1)
    _frozen_check(metric, request, expected, PERCENT_TOLERANCE, run)
    assert metric["result_unit"] == "%"
    assert set(metric["source_refs"]) == {source}
    assert expected.quantize(Decimal("0.01")) == Decimal("10.98")


def test_fr02_frozen_msft_capex_over_operating_cash_flow():
    """T-FR02-RATIO: MSFT capex over operating cash flow, FY2026, displays 63.38%."""
    run = _frozen_run("MSFT", "msft-ratio")
    source = "sec:10-K:0001193125-26-323660:cashflow:line23"
    period = _frozen_period("year", "2025-07-01", "2026-06-30", "FY2026")
    request = _request("ratio", [
        _frozen_operand("numerator", "115948", "USD_millions", period, source,
                        "PaymentsToAcquirePropertyPlantAndEquipment"),
        _frozen_operand("denominator", "182935", "USD_millions", period, source,
                        "NetCashProvidedByUsedInOperatingActivities"),
    ])

    metric = _verified(_owner().verify_metric(request, run))
    expected = Decimal(100) * Decimal(115948) / Decimal(182935)
    _frozen_check(metric, request, expected, PERCENT_TOLERANCE, run)
    assert metric["result_unit"] == "%"
    assert set(metric["source_refs"]) == {source}
    assert expected.quantize(Decimal("0.01")) == Decimal("63.38")


def test_fr02_frozen_aapl_bollinger_gap_both_directions():
    """T-FR02-DELTA: AAPL 2026-11-10 boll_ub - Close is +4.526, reversed is -4.526."""
    quote = _frozen_period("instant", AS_OF, AS_OF, f"{AS_OF} close")
    source = "snapshot:aapl:2026-11-10"

    up_run = _frozen_run("AAPL", "aapl-gap-up")
    up_request = _request("price_delta", [
        _frozen_operand("current", "352.771", "USD", quote, source, "boll_ub"),
        _frozen_operand("reference", "348.245", "USD", quote, source, "Close"),
    ])
    up = _verified(_owner().verify_metric(up_request, up_run))
    expected = Decimal("352.771") - Decimal("348.245")
    up_value = _frozen_check(up, up_request, expected, PRICE_TOLERANCE, up_run)
    assert up_value > 0, "an absolute-value replacement shows here"
    assert up["result_unit"] == "USD"
    assert set(up["source_refs"]) == {source}

    down_run = _frozen_run("AAPL", "aapl-gap-down")
    down_request = _request("price_delta", [
        _frozen_operand("current", "348.245", "USD", quote, source, "Close"),
        _frozen_operand("reference", "352.771", "USD", quote, source, "boll_ub"),
    ])
    down = _verified(_owner().verify_metric(down_request, down_run))
    down_value = _frozen_check(down, down_request, -expected, PRICE_TOLERANCE, down_run)
    assert down_value < 0, "the sign must follow the operand roles"
    assert down["result_unit"] == "USD"
    assert set(down["source_refs"]) == {source}


# --- Real graph with the two inputs that carry no usable metadata --------
# Same offline inputs and real graph as the normal-path case: the income
# statement gives fiscal year ends only, and the snapshot gives no quote
# currency. The run is expected to finish and publish a report while the
# verified registry and the manager's list stay empty and the report shows no
# metrics row. A tool that never ran, a tool error or an empty report is a
# failure here, not a pass.

TRADING_ROW_PREFIX = "- Latest trading row used:"


def _snapshot_trading_date(text):
    """The trading day read from the snapshot reply's own "Latest trading row used" line.

    Only the reply's own line is used, never the requested date. A trailing
    time is dropped, leaving the date to compare. Returns None when the line
    is absent, so a reply that does not carry it fails loudly.
    """
    for line in str(text).splitlines():
        stripped = line.strip()
        if not stripped.startswith(TRADING_ROW_PREFIX):
            continue
        value = stripped[len(TRADING_ROW_PREFIX):].strip()
        if not value:
            continue
        return value.split("T")[0].split(" ")[0].strip()
    return None


def test_fr02_e2e_missing_source_metadata(tmp_path, monkeypatch):
    """Both analyst inputs lack usable metadata: the run finishes, nothing is verified.

    Checked on the real returns: each tool called once and succeeded, the
    statement's own two rows, the snapshot's own trading day and its finite
    Close and boll_ub, the run identity, the two analyst reports, the
    Portfolio Manager's decision and the saved report. Only the controlled
    fields are checked: prose may mention numbers without making them metrics.
    """
    from langchain_core.messages import ToolMessage

    called = _e2e_offline_sources(monkeypatch)
    model = E2EScriptedModel()
    graph = _e2e_graph(tmp_path, monkeypatch, model)

    state, signal = graph.propagate(TICKER, E2E_TRADE_DATE)
    report_path = graph.save_reports(state, TICKER, tmp_path / "report", html=False)
    report_text = report_path.read_text(encoding="utf-8")

    # 1. This run really called both tools, once each.
    assert model.tool_calls_made.count(MARKET_TOOL) == 1, (
        f"expected one {MARKET_TOOL} call, saw {model.tool_calls_made}")
    assert model.tool_calls_made.count(STATEMENT_TOOL) == 1, (
        f"expected one {STATEMENT_TOOL} call, saw {model.tool_calls_made}")

    # 2. Both tools returned a real, non-error ToolMessage.
    by_name = {}
    for message in model.received:
        by_name.setdefault(message.name, []).append(message)
    assert MARKET_TOOL in by_name, f"{MARKET_TOOL} returned no ToolMessage"
    assert STATEMENT_TOOL in by_name, f"{STATEMENT_TOOL} returned no ToolMessage"
    snapshot_message = by_name[MARKET_TOOL][-1]
    statement_message = by_name[STATEMENT_TOOL][-1]
    assert isinstance(snapshot_message, ToolMessage)
    assert isinstance(statement_message, ToolMessage)
    assert getattr(snapshot_message, "status", "success") != "error", (
        "the snapshot tool result is an error message")
    assert getattr(statement_message, "status", "success") != "error", (
        "the statement tool result is an error message")

    # 3. The statement reply's own two rows, on their own periods.
    by_period = _cost_of_revenue_by_period(statement_message.content)
    assert by_period.get("2025-05-31") == "100", f"prior row is {by_period!r}"
    assert by_period.get("2026-05-31") == "125", f"current row is {by_period!r}"

    # 4. The snapshot's own trading day, read from the reply and compared with
    #    this offline run's trading date; the requested date is not used.
    trading_day = _snapshot_trading_date(snapshot_message.content)
    assert trading_day is not None, (
        "the snapshot reply has no 'Latest trading row used' line")
    assert trading_day == E2E_TRADE_DATE, (
        f"the snapshot's own trading day is {trading_day!r}, not {E2E_TRADE_DATE!r}")

    # 5. The snapshot reply's own two finite fields.
    snapshot = _two_column_rows(snapshot_message.content, SNAPSHOT_FIELDS)
    assert set(snapshot) == set(SNAPSHOT_FIELDS), (
        f"the snapshot table lacks {sorted(set(SNAPSHOT_FIELDS) - set(snapshot))}")
    close_value = _finte_decimal(snapshot["Close"])
    upper_band = _finte_decimal(snapshot["boll_ub"])
    assert close_value.is_finite() and upper_band.is_finite()

    # 6. The run really executed: the path was read and every output has content.
    assert "ohlcv" in called, "the snapshot path read no prices"
    assert STATEMENT_TOOL in called, "the statement path was not called"
    assert state.get("market_report", "").strip(), "the market analyst filed no report"
    assert state.get("fundamentals_report", "").strip(), "the fundamentals analyst filed no report"
    assert "PortfolioDecision" in model.calls
    assert state["publication_status"] == "BLOCKED"
    assert state["publication_reason"] == "INSUFFICIENT_EVIDENCE"
    assert not state["final_trade_decision"]
    assert report_text.strip(), "the saved report is empty"

    # 7. This run's identity, by its own course_run.
    course_run = state.get("course_run")
    assert course_run, "the run carries no course_run"
    assert course_run.get("run_id"), "the run carries no run_id"
    assert course_run.get("ticker") == TICKER, "course_run names another ticker than this run"
    assert course_run.get("as_of_date") == E2E_TRADE_DATE, (
        "course_run carries another date than this run")

    # 8. Neither input had usable metadata, so nothing was verified and the
    #    manager's list is present but empty.
    registry = state.get("verified_metrics")
    listed = state.get("portfolio_verified_metrics")
    assert isinstance(registry, dict), "the parent state carries no verified_metrics registry"
    assert registry == {}, f"the run verified records it should not have: {sorted(registry)}"
    assert isinstance(listed, list), "the parent state carries no portfolio_verified_metrics list"
    assert listed == [], f"the manager listed records it should not have: {listed}"

    # 9. The report's metrics table has no row. Prose may mention numbers; only
    #    the controlled table is judged.
    table = _verified_metrics_table(report_text)
    assert not table, f"the report shows metrics rows: {table}"
