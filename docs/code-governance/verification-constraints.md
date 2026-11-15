# Verification constraints

The [D1 registry](../req/requirements.yaml) defines the acceptance criteria. The [trace matrix](../architecture/trace-matrix.md) maps them to components and monitors. The cases below are planned, not test results.

Before implementation, a human reviewer approves the plan and independently specified tests. Record the approver, time and link to the reviewed revision. Each test must name the FR, NFR or INV it verifies in its name, docstring or documented case mapping. Every fit criterion must have at least one test and every invariant at least one negative test that fails if the enforcement is bypassed. Confirm that positive controls pass; a system that rejects everything does not satisfy acceptance.

| ID | Minimum offline checks | Evidence to retain |
| --- | --- | --- |
| FR-01 | Exercise valid rating plus resolvable evidence, illegal rating, missing reference, unknown ID and cross-run ID at both entry points. Check approved trace from recommendation to source, and verify refusal status and reason. | Case IDs, CLI/API outcomes and trace example |
| INV-01 | Inject a rejected Buy; assert no official rating in CLI, API, report or decision memory. Demonstrate that bypassing the gate or leaking to any sink fails a test. | Negative assertions for all four sinks |
| FR-02 | Freeze source operands and recompute all four D1 examples with the stated tolerances and formulas. Test signed subtraction, equivalent reporting periods, mismatched periods/units, missing provenance, nonfinite operands, nonpositive denominators, altered values, unknown IDs and newly constructed invalid records. Assert downstream fields and report use the same verified ID; invalid operands return UNVERIFIABLE. | Operand provenance, expected result and tolerance per fixture; verified-record and report assertions |
| FR-03 | Test 0/3, 1/3, 2/3 and 3/3 sources, genuine neutral, empty/error responses and wrong symbol/window. Check source reasons and consistency across state, report and downstream input. Assert null is not imputed or averaged and valid market/financial analysis continues. | Input fixtures, coverage and score assertions, continuation evidence |
| NFR-01 | With limit 3, verify exactly three requests can complete; a fourth is not sent, yields BUDGET_EXHAUSTED, and no official rating appears. Check independent concurrent runs, supported retry configuration and settlement exclusion. Count at fake transport, not at the UI. | Dispatch trace with scoped request counts and outcomes |
| INV-02 | Race two calls for the final slot; assert at most one outbound request. Include a deterministic synchronization point so a reservation bypass cannot pass by scheduling luck. | Concurrent send assertions and isolation evidence |
| NFR-02 | Cover both designated call sites with short, reducible, irreducible and multibyte examples. Measure final UTF-8 messages against 65536 bytes under the proposed config, excluding bound schemas. Assert identical reduction for identical input, full required-block retention, intact tool pairing and zero sends/debits for CONTEXT_TOO_LARGE. | Before/after byte counts and mandatory-block assertions |

Verification has three tiers:

1. **Structural:** validate the D1 registry against its schema and check unique IDs; check lint, typing and dependencies. Inspect import boundaries, one owner per responsibility, the shared publication/dispatch routes and OpenCode's effective role/path permissions. For safety-path changes verify contracts, API surface, permission least privilege and security checks. An approval request must not grant authority to frozen files.
2. **Regression:** for every implementation round run all suites from earlier rounds, including upstream `tests/` and accumulated `test/offline/`, with zero regressions. Record exact commands, revision, environment, skipped tests and results. Air-gapped tests use fixed inputs, fake transports and isolated state; a live smoke run is separate and cannot replace offline coverage. An unavailable check is not a pass.
3. **Behavioral:** apply the table to each affected feature and together at the two shared boundaries. A context rejection must not spend a request slot. A budget stop or release rejection must not publish a recommendation. Compare performance only with equivalent inputs, config, and completion; report early exits separately. Prompt/model changes require a fixed semantic evaluation set and agreed thresholds before merge; check source support separately from existence of an ID, and require zero safety escapes. Agree and record any quality threshold not already in D1 before running the evaluation.

Record findings and verdict in the [PR review memo](../review-memo.md), significant defects in the [bug diary](../bug-diary.md), and deferred risks in the [debt register](../debt-register.md). GitHub enforcement of these checks is part of D7; this document does not claim any check has run or is configured as required.

## Stable planned case IDs and concrete controls

These IDs are referenced by D1. They are test-design identifiers, not executable tests or pass receipts. The owner must freeze exact fixtures and assertion locations in the plan before approval. Keep raw online observations separate from synthetic inputs.

| Case IDs | Fixed design / expected result |
| --- | --- |
| T-FR01-VALID, T-FR01-RATING, T-FR01-MISSING, T-FR01-REFERENCE, T-FR01-SINKS | One current-run evidence E1 and accepted argument A1 -> legal rating publishes; illegal rating, absent argument, unknown/cross-run E1 -> refusal. Inspect CLI/API/report/memory, not just the gate return. |
| T-FR02-YOY, T-FR02-RATIO, T-FR02-DELTA | Synthetic controls: comparable prior 100/current 125 -> 25%; same-period numerator 20/denominator 80 -> 25%; same-unit current 10.125/reference 5.599 -> +4.526, reverse -> -4.526. These are not real-company source reproductions. |
| T-FR02-INVALID, T-FR02-IDENTITY | Zero/negative denominator, NaN/Inf, missing provenance, period/unit mismatch -> UNVERIFIABLE; changed value, unknown ID and newly forged record cannot enter verified fields. Original four company examples remain pending their operands. |
| T-FR03-COVERAGE | All source-validity combinations (8 combinations for 3 sources): 0 -> NO_DATA/UNKNOWN/null; 1 or 2 -> PARTIAL_DATA with exact count; 3 -> AVAILABLE. Reddit subreddits never increase denominator above 3. |
| T-FR03-INVALID | Empty payload, explicit vendor error placeholder, unsupported history, wrong ticker, before-start/at-end-boundary timestamps and unverifiable metadata do not count; test C3 inclusive calendar days and frozen clock. Reasons remain distinguishable. |
| T-FR03-NEUTRAL | Valid in-window evidence and an actual measured Neutral/5.0 remain legal; do not reject all scores to satisfy missingness. |
| T-FR03-PROPAGATION | Authoritative state, analyst message, downstream and report agree on null; no imputation/mean; old run cannot supply a score. NO_DATA plus valid market/fundamental evidence continues and may pass C1. Exercise structured and free-text paths. |
| T-FR03-SCORE | Nonzero coverage plus missing/invalid assessment -> UNKNOWN/null with the original coverage retained; reject NaN, Infinity, negative or >10 score. |
| T-NFR01-BOUNDARY, T-NFR01-RETRY | Limit 3 and actual fake transport with 3/4 attempts; count application retries and structured-to-free-text fallback as separate outgoing attempts. Verify supported SDK retry settings. |
| T-NFR01-ISOLATION, T-NFR01-FAILURE, T-NFR01-RESUME | Concurrent runs isolate counters; after-send provider failure consumes a slot; pre-send cancellation is not an extra send. Resume is disabled or restores spent count without reset. Settlement exclusion is explicit. |
| T-NFR02-SHORT, T-NFR02-REDUCE, T-NFR02-REJECT, T-NFR02-UTF8 | Freeze normalized message bytes with cap 65536: below/exactly/above boundary, optional reducible history, mandatory irreducible content, Chinese/emoji UTF-8. Same input/config -> identical prepared bytes. |
| T-NFR02-PAIRING, T-NFR02-ORDER | Required-block hashes and tool pairs survive; both designated sites tested; rejected context produces zero actual sends/reservations/debits, even when only one budget slot remains. |
| T-INV01-BYPASS | Deliberately bypass one official sink's gate in a controlled test: the negative assertion must fail. Restore code; never merge the deliberate violation. |
| T-INV02-RACE | Deterministically synchronize two contenders for one remaining slot; only one fake transport send is allowed, independent of scheduler luck. |

## Execution, collection and semantic changes

Record Python/dependency versions, source SHA, test/fixture revision, clock, configuration and completion status. Commands below apply **after** executable course tests have been added; an empty directory, exit code 5 or skipped scaffold is not a pass:

- Collection: `python -m pytest --collect-only -q test/offline`.
- Offline regression: `python -m pytest -q tests test/offline -m "not integration"`.
- Live checks, explicitly authorized with private credentials: `python -m pytest -q test/live -m integration`.
- Patch hygiene: `git diff --check`; include untracked files in review separately.

The current default `testpaths = ["tests"]` does not collect `test/offline`. D7 must explicitly collect accumulated course tests and fail when required cases are absent/skipped. Do not install dependencies or make external requests during deterministic offline checks. Use isolated caches/memory and fake transports; actual fake-send counts are independent evidence.

Before any application prompt/model change merges, freeze an evaluation revision in Git with exact inputs and expected facts, plus the model/config/prompt revisions. Proposed initial semantic set: valid citation, unknown citation, zero sentiment sources, genuine neutral, partial coverage, synthetic YoY and invalid metric provenance. Supply complete synthetic content and expected fact/rubric annotations, not only scenario names; these executable/evaluation fixtures are still to be prepared and approved. Proposed thresholds: 100% required-field/coverage agreement, 100% citation resolvability where publication is allowed, zero safety escapes and zero contradiction of declared missing-data facts; human source-support review uses a predeclared rubric and threshold before the first evaluation. Reference existence alone is not semantic faithfulness. Do not tune thresholds after seeing a result or count early refusal as a quality/performance gain.

## D7 gate handoff — not implemented by this document

| Teacher gate (Project P10) | Required integration/evidence before applicable merge |
| --- | --- |
| Test approval | Link the human approval of exact plan/test revision before first implementation; mutable PR text alone is insufficient evidence |
| Static/security | Lint, typing and dependency checks; contract/security/API/permissions checks for safety-path PRs |
| Schema | JSON Schema validation **plus** unique requirement IDs and resolved C0–C5/case references |
| Semantic evaluation | Fixed, versioned inputs, expected facts/rubric and frozen thresholds for application prompt/model changes |
| Regression | Upstream and all previous course offline suites collected, no unexplained missing/skipped acceptance cases |
| AI-use log | Code/application-prompt PR updates the log with real tool/session and scope; missing entry blocks |

Human administrators must configure required checks and safety review/ADR protection, and verify them with a controlled failing PR. Six green upstream checks do not establish these six course gates. This documentation PR does not install new checks or claim branch protection is active.
