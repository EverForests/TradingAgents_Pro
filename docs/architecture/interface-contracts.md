# Shared interface contracts

Status: **interface v1.0 — selected proposal for team confirmation**. This file fixes the shared record names, fields, defaults and callable boundaries below. They are documentation contracts, not implemented classes or passing tests. Preserve the five D1 requirements. Use JSON-compatible mappings at shared boundaries; internal dataclasses, TypedDict or existing Pydantic models are permitted through adapters that preserve these exact fields and semantics. ADR-001 governs the choice. Team confirmation does not replace each feature plan/test approval.

## Ownership and integration

| Contract | Authority | Producers and consumers |
| --- | --- | --- |
| C0 run identity and outcome | Run coordinator | All five owner modules, CLI, Python, report and memory |
| C1 evidence and publication | FR-01 publication gate | Analyst evidence, accepted arguments, candidate, all official sinks |
| C2 verified metrics | FR-02 metric registry | Fundamentals inputs, controlled downstream fields and metric table |
| C3 sentiment coverage | FR-03 coverage component | Existing source adapters, analyst, state, report and downstream agents |
| C4 dispatch budget | NFR-01 request-budget component | Both model tiers and every in-scope transport send |
| C5 prepared context | NFR-02 context component | Analyst closure and neutral risk debater, then C4 |

Shared-file edits (`agents/state.py`, `agents/schemas.py`, graph/client adapters and reporting) need an integration owner agreed by the team. Feature owners propose narrow patches; the coordinator preserves all approved contracts when combining them. Contract IDs and the v1 callable boundaries below are stable for the proposed first release. Per-task plans identify exact adapter paths. Follow the meeting arrangement of LIU Huansong as integrator unless the team changes it; feature owners do not independently replace shared state/schema/report files.

## C0 — identity, state and errors

Every authoritative record carries `run_id`, normalized `ticker` and `as_of_date`. Evidence and metric IDs are only resolvable inside that run. Never retrieve a matching-looking ID from a previous run. A restarted run gets a new ID. A metered checkpoint resume is disabled until the counter/state restoration contract is implemented and approved.

Keep three concepts separate:

- Execution: RUNNING, COMPLETED, BUDGET_EXHAUSTED, CONTEXT_TOO_LARGE or FAILED. COMPLETED describes the workflow, not approval of a recommendation.
- Publication: PENDING, APPROVED or BLOCKED, with reason codes. An official rating is present only on APPROVED.
- Data coverage: NO_DATA, PARTIAL_DATA or AVAILABLE for optional sentiment. NO_DATA alone is not a failed run or a publication rejection.

A terminal budget/context failure suppresses the official rating. Valid market/financial evidence can still support publication when sentiment is unavailable, provided C1 passes. Diagnostics are explicitly nonofficial; rejected candidate prose must not leak into an official rating field, final-decision section or decision memory. Fixing a contract requires a versioned D1/D2/test update before dependent work continues.

## C1 — evidence, accepted arguments and publication

An EvidenceRecord contains `run_id`, `evidence_id`, source kind/vendor, request ticker/window, source locator (URL, document/field or fixture reference), observed period and source content/reference. Assigning an ID does not make empty, failed or unrelated content valid. Missing-source diagnostics can explain absence but are not substantive market evidence.

An AcceptedArgument contains `run_id`, `argument_id`, the claim and a nonempty list of evidence IDs that resolve in the current run. This version verifies reference integrity, not whether a source semantically proves an investment conclusion. A candidate contains an explicit rating and accepted argument IDs. Use the existing five-tier vocabulary: Buy, Overweight, Hold, Underweight, Sell. REVIEW and arbitrary free text are not publishable ratings.

The deterministic gate returns one authoritative PublicationResult: identity, publication status, reasons, approved rating or null, and validated argument/evidence references. Invalid rating uses INVALID_RATING; missing, unknown, cross-run or unaccepted required references use INSUFFICIENT_EVIDENCE. Diagnostics may retain rejected values privately, but official consumers receive no rejected rating. All four sinks (CLI, Python result, saved official report, decision memory) consume this same result. Structured output, free-text fallback and streaming/final display paths cannot bypass it.

FR-02 adds verified numerical records; FR-01 must not label arbitrary model prose as verified arithmetic. FR-03 missingness does not automatically invalidate other evidence. The v1 result fields below are common to all sinks; name exact sink adapter edits in the relevant feature plan and test each one.

## C2 — verified metrics

Input: metric kind (YoY, ratio or signed difference), raw operands, source locators/fields, periods, units/currencies and run identity. Use source precision, preferably Decimal-compatible strings. Output: VERIFIED with immutable `metric_id`, normalized operands, formula, result/unit/period and provenance, or UNVERIFIABLE with a reason and no verified value.

- YoY = 100 * (current / prior - 1); compare the same quarter in adjacent years or comparable full years.
- Ratio = 100 * numerator / denominator; record dimensional/unit compatibility and period alignment.
- Signed difference = current - reference; preserve sign and price unit.
- YoY/ratio denominators must be positive in this release. Reject nonfinite values, absent provenance, incompatible units or incomparable periods.
- Percentage tolerance is 0.1 **percentage points**, not relative percent. Price-difference tolerance is 0.01 price units. Preserve calculation precision separately from displayed rounding.

Only the owner registry creates authoritative verified records. Consumers resolve IDs against it; a model-supplied value, changed value, unknown ID or new arbitrary ID must not create verification authority. Retain original records for the run and reject conflicting writes.

The reported 105.85%, 10.98%, 63.38% and 4.526 remain provisional examples until original operands are supplied and independently recomputed. Synthetic formula tests may run first, but cannot be reported as reproductions of those companies' original observations. No basis-point feature or arbitrary narrative-math parser is added.

## C3 — sentiment source coverage and nullable score

Three logical sources are `news`, `stocktwits` and `reddit`; Reddit's three subreddits collectively count as one source. Record the actual news vendor; a configured fallback must not be mislabeled Yahoo. Do not add another data provider. For like-for-like baseline checks, record the chosen vendor route.

Each SourceOutcome contains identity, source ID, requested window, availability, valid-record count, reason codes and shareable evidence locators. A source counts once when it returns at least one substantive item attributable to the requested ticker and valid window. Ticker association may come from explicit item metadata or an approved, request-bound adapter; arbitrary substring matches and model assertions are insufficient. Agree and test the supported adapter metadata/placeholder patterns before implementation. An opaque nonempty string is not automatically valid data.

Use the baseline's seven-day-back start and end date: [start 00:00 UTC, end + 1 day 00:00 UTC). AAPL as-of 2026-11-10 therefore covers 2026-11-03 through 2026-11-10. Freeze the clock for date-dependent fixtures. Historical undated content cannot prove window validity. Do not silently tighten or change the baseline date semantics; document any justified change and test boundaries.

Reasons distinguish at least EMPTY, FETCH_ERROR, WINDOW_UNSUPPORTED, OUT_OF_WINDOW, TICKER_MISMATCH and UNVERIFIABLE_METADATA. Keep actual vendor failure distinct from a successful fetch with no matching items. Never claim these statuses prove that no real-world messages/news exist.

| Valid logical sources | coverage_status | Sentiment output |
| --- | --- | --- |
| 0/3 | NO_DATA | overall_band UNKNOWN; overall_score null |
| 1/3 or 2/3 | PARTIAL_DATA | Coverage remains explicit; any measured score uses valid evidence only |
| 3/3 | AVAILABLE | Coverage available; score still requires a valid assessment |

Coverage is authoritative data state; the model cannot increase it. With nonzero coverage, permit a finite 0–10 score and an existing band only when an assessment was produced. If assessment fails or its score is absent/invalid, use UNKNOWN/null while retaining the nonzero coverage and an assessment-failure reason; do not mislabel this NO_DATA. A genuine measured Neutral/5.0 remains legal.

Missing scores never become 0 or 5 and never enter a numerical mean. Structured state, analyst message, downstream prompt and persisted/rendered report must agree. Handle nullable scores without numeric-format errors. Apply the contract to structured **and** free-text fallback; model narrative cannot override authoritative coverage. Keep the existing sentiment_report text as a compatibility view; the new sentiment_assessment record below is authoritative. Both must agree. Internal schema adaptation may change, but the v1 shared record does not drift silently.

The original baseline stores `sentiment_report` as text and requires a nonnull numeric SentimentReport score. Updating only the prompt cannot establish this contract. No raw social bodies or credentials belong in public evidence. Missing optional sentiment does not stop otherwise valid market/fundamental analysis; C1 still decides publication.

## C4 — atomic per-run model dispatch

Supported scope: one single-stock main analysis, both model tiers, structured/fallback requests and application retries. Count actual outgoing model attempts, not nodes, tool invocations, callbacks or tokens. Historical settlement is excluded. Disable SDK/transport implicit retries in supported course runs; unsupported hidden-retry modes are outside the verified configuration, not silently compliant.

Budget state: positive integer `limit`, charged sends, active reservations and exhaustion. Atomically reserve capacity before a send so charged sends plus active reservations cannot exceed limit. A reservation transitions once to a charged attempt at the outbound boundary. A provider error after an attempted send consumes the slot; do not refund an ambiguous send. A cancellation proven to precede transport may release an unused reservation. Validate C5 first so context rejection obtains no reservation.

No slot => BUDGET_EXHAUSTED, no request, no official recommendation. Limit 3 allows exactly 3 attempts; the fourth is refused. Concurrent runs do not share counters. Include application fallback/retry attempts separately. C4 does not promise a monetary or token cap. Transport probes must count actual fake sends and check reservation cleanup rather than trusting the reported counter alone.

## C5 — deterministic prepared context

Initial integration sites: analyst closure and `risk_mgmt/neutral_debator.py` only. Other analyst turns and risk roles are not implicitly covered. Before reserving C4, fully expand/convert the scoped final message sequence into one agreed provider-facing representation.

Canonical v1 measurement: the final provider-facing message array encoded as JSON with ensure_ascii=False, sort_keys=True, separators=(comma, colon) without optional whitespace, allow_nan=False, then UTF-8. Use the ChatMessage representation below and freeze byte fixtures before implementation. Do not measure before template expansion or change representation after measuring. Tool schemas and other separately bound fields are excluded from this message metric and must be recorded/bounded separately; this is not a cap on the whole HTTP body.

Required blocks: role/task identity; standing safety/publication rules; ticker/date/run identity; current required evidence/verified metrics/source coverage; and the active tool-call/result exchange. Optional blocks: explicitly marked older discussion/history. A tool-call/result pair is indivisible; if a member is required, preserve the whole pair. Text-wrapped tools retain name, arguments and corresponding result. Removing context cannot delete authoritative evidence/state from storage.

At the proposed 65536-byte test cap: short input passes unchanged. If oversized, remove optional groups oldest first (stable original index for ties), reassemble, reinject critical constraints and remeasure. Do not summarize required evidence with another unmetered model call. If required blocks cannot fit or pairing cannot be preserved, return CONTEXT_TOO_LARGE; zero send, reservation and debit. Same normalized input/config produces identical prepared output. Run final retention/pairing checks before C4.

This byte cap does not implement the separate D2 token-budget requirement. ADR-001 records that architecture design and the remaining tokenizer/model-capacity validation. Do not infer token counts from bytes/4 or claim provider safety from 64 KiB alone.

## Contract-change and approval record

Before implementation, record requirement IDs, contract revision, baseline SHA, exact read/edit paths, fixture/case revision, reviewer and approval time. Approval is a human decision about that revision, not an agent summary or a default assent. Document-only preparation may propose contracts; it does not approve feature implementation. Reapprove changes to shared fields, thresholds, test expectations, safety paths or dependencies. Feature PRs link the approved plan and actual evidence; the coordinator runs integrated regressions before release.


## V1 shared record layout

Version field: `contract_version = "1.0"`. Shared artifacts carry `run_id`, normalized `ticker` and ISO `as_of_date` copied from RunContext. Nonsecret IDs are opaque strings; consumers must not infer meaning from their spelling. Dates use YYYY-MM-DD. A missing optional value is explicit null; a missing required field is an invalid record. Lists have deterministic order; ID-indexed registries are mappings, not unordered output prose.

| Record | Required shared fields beyond identity | Owner |
| --- | --- | --- |
| RunContext | contract_version, execution_status, request_limit (positive integer) | Existing graph/run entry; integration by coordinator |
| EvidenceRecord | evidence_id, source_kind, vendor, source_ref, content_ref, window_start, window_end | FR-01 collection/index adapter |
| AcceptedArgument | argument_id, claim (nonempty text), evidence_ids (nonempty list) | FR-01 validates against run-local evidence; a model flag is not acceptance |
| CandidateDecision | rating (untrusted string or null), argument_ids | Model/adapters produce; C1 decides |
| PublicationResult | publication_status, reason_codes, rating (allowed string or null), argument_ids, evidence_ids | FR-01 |
| Operand | role, value (finite decimal string), unit, period, source_ref, field_ref | FR-02 input adapter; roles current/prior/numerator/denominator/reference |
| MetricRequest | kind (yoy/ratio/price_delta), operands | FR-02 input |
| VerifiedMetric | metric_id, kind, operands, result_value (decimal string), result_unit, formula, source_refs | FR-02 immutable run-local registry |
| MetricResult | status (VERIFIED/UNVERIFIABLE), metric (VerifiedMetric or null), reason_codes | FR-02 |
| SourceOutcome | source_id, window_start, window_end, available (bool), valid_record_count, reason_codes, evidence_refs | FR-03 normalization adapter |
| SentimentCoverage | coverage_status, valid_sources, total_sources (=3), sources (mapping keyed news/stocktwits/reddit) | FR-03 deterministic coverage |
| SentimentAssessment | all SentimentCoverage fields, assessment_status (MEASURED/UNKNOWN), overall_band, overall_score, confidence, assessment_reason_codes, narrative | FR-03 deterministic finalization |
| ContextBlock | group_id, required (bool), messages (list of ChatMessage); grouping metadata is never sent to the model | NFR-02 scoped adapter |
| PreparedRequest | status (READY/CONTEXT_TOO_LARGE), messages (list or null), message_bytes, original_message_bytes, dropped_group_ids, required_groups_ok | NFR-02 or nonreducing adapter |
| Reservation | reservation_id, run_id, state (reserved/charged/cancelled); opaque to other features | NFR-01 |

`Operand.period` is `{kind, start, end, label}`: kind is quarter/year/instant, start/end are ISO dates, and label records the source's fiscal period or quote timestamp. Currency and scale are part of unit (for example USD vs USD_millions); conversion must be explicit and preserve original operands. Do not silently take abs(capex), invent comparable periods or round source values to make a fixture match. An EvidenceRecord source_ref identifies the source, while content_ref locates the retained shareable material/fixture; an ID with no resolvable retained material is insufficient.

For SentimentAssessment, overall_band is one existing measured band or UNKNOWN. overall_score is a finite float in [0,10] for MEASURED, otherwise null. confidence keeps the existing low/medium/high vocabulary; UNKNOWN uses low and is not a measured weak-neutral signal. Missing sources are unavailable with reasons; valid sources have valid_record_count >=1. Missing uncollected source entries are normalized as unavailable with NOT_COLLECTED rather than increasing the denominator or silently disappearing. Extra providers do not count as fourth sources. Source order is news, stocktwits, reddit.

`ChatMessage` contains provider-facing role, content and, when present, name/tool_call_id/tool_calls/reasoning_content. Preserve content strings or JSON-compatible content blocks without paraphrasing. Preserve each tool call's id, type, function name and arguments plus the paired tool result. Reasoning fields required by the selected provider's tool round-trip are mandatory if present. Do not add ContextBlock metadata to ChatMessage. The cap measures the agreed canonical message representation, not HTTP whitespace, the whole body, output tokens or hidden provider overhead.

## V1 callable boundaries (specification signatures, no implementation)

Inputs are read-only to consumers. Return the declared records; do not attach extra authoritative fields through prose. Signatures below describe Python-callable boundaries; they do not create five network services.

| Planned owner | Public v1 call | Behavior |
| --- | --- | --- |
| publication_gate.py | validate_argument(argument, evidence_index, run) -> AcceptedArgument or validation failure | Check current-run references before acceptance |
| publication_gate.py | evaluate_publication(candidate, argument_index, evidence_index, run) -> PublicationResult | Recheck accepted references and rating; one result for all official sinks |
| verified_metrics.py | verify_metric(request, run) -> MetricResult | Compute from validated operands, register only verified records |
| verified_metrics.py | resolve_metric(metric_id, registry, run) -> VerifiedMetric or null | Resolve trusted ID; never accept a caller-supplied replacement value |
| sentiment_coverage.py | normalize_source(raw_result, source_id, run, window_start, window_end) -> SourceOutcome | Derive availability from collection receipts and approved metadata rules |
| sentiment_coverage.py | build_sentiment_coverage(sources, run) -> SentimentCoverage | Count three logical sources once each |
| sentiment_coverage.py | finalize_sentiment(coverage, model_assessment_or_null, run) -> SentimentAssessment | Coverage is authoritative; validate score/band; no imputation |
| context_limit.py | prepare_context(blocks, max_message_bytes=65536) -> PreparedRequest | Only the two scoped sites reduce; reject irreducible context |
| request_budget.py | RequestBudget(run_id, limit); try_reserve() -> Reservation or null; charge_attempt(ticket); cancel_before_send(ticket); snapshot() | Atomic lifecycle; cancellation only when transport is known not to have started |
| request_budget.py | dispatch(prepared, budget, send) -> sender's normal response type | Require READY, reserve, charge at attempt boundary, invoke send exactly once; refusal is a typed failure, never a Hold/default rating |

The sender callable accepts the prepared messages and performs exactly one underlying request with SDK retries disabled. Application fallback/retries call dispatch again. Dispatch failure types are BudgetExhausted, ContextTooLarge and ProviderFailure (defined in the responsible owner module); the graph entry maps them to C0 terminal state. Provider failures after an ambiguous attempt remain charged. Snapshot separates charged attempts, known actual sends and unknown-delivery attempts; a connection attempt is not claimed to be a billed model response.

Publication evaluation first respects C0 terminal failure/incomplete execution (BUDGET_EXHAUSTED, CONTEXT_TOO_LARGE or RUN_NOT_COMPLETE); then rejects an invalid rating; then rejects insufficient references. APPROVED has an allowed rating, nonempty accepted argument/evidence references and no rejection reasons. BLOCKED always has rating=null. An incomplete workflow cannot publish an earlier candidate.

## V1 graph handoff and compatibility

Add the following keys to the existing AgentState through narrow integration edits: course_run (RunContext), evidence_index, argument_index, verified_metrics, sentiment_assessment and publication_result. These are separate state keys; do not have parallel nodes overwrite an entire common nested dictionary. Existing nodes own their existing report strings. New owner records are not reconstructed from those strings. Avoid new dependencies or replacement of the orchestrator.

For sentiment, the analyst emits sentiment_assessment and renders its legacy sentiment_report from that same record, including the model-message/report views. At 0/3, the selected v1 path skips the sentiment model call and creates a deterministic missing-data narrative with UNKNOWN/null. This is an FR-03 implementation decision, not an extra feature. With data, finalize the model assessment while preserving coverage; provider/free-text fallback cannot restore a made-up default score. The FR-03 task plan tests schema/renderer compatibility before selecting the internal Pydantic adaptation. FR-01 can publish from valid non-sentiment evidence when its own gate passes.

The shared model client receives PreparedRequest. At the two NFR-02 sites use prepare_context; elsewhere use a nonreducing READY adapter so NFR-01 covers all sends without accidentally applying a 64 KiB cap to every call. All branches then use the same C4 dispatch boundary. Tests can use fixed fake producers/consumers until integration, but combined graph acceptance needs the real connected owner modules.

## Working defaults and limits with different purposes

| Setting | V1 choice / purpose | Change rule |
| --- | --- | --- |
| Application baseline | 9fa1196; retain existing package layout | New baseline needs explicit rationale and regressions |
| Local environment | Reuse verified Python 3.11 environment; record exact patch/dependencies | Align a team-approved baseline when needed, no automatic reinstall |
| Course profile model | School CS5351/DeepSeek-V4-Flash for both tiers; explicit thinking-disabled request after compatibility check | Record actual settings; do not infer backend revision from alias |
| Course profile output allowance | 4096 tokens as initial run-profile choice, not an acceptance threshold | Raise only with a truncation reason and recorded configuration |
| Product request_limit | 40 per single-stock run as initial configurable profile | Revisit against completed baseline; D1 hard rule is actual requests <= configured limit |
| NFR-01 boundary fixture | limit 3, exactly-three succeeds, fourth refuses | Fixed test condition; not the normal application's default |
| NFR-02 message cap | 65536 bytes at analyst closure and neutral risk role | Normal configurable setting; changes update the affected fixtures/contracts |
| Token architecture proposal | 16384 input tokens, 80% trigger remains unactivated design pending counting/capacity evidence | Not an automatic global gate or an extra feature |
| Reproduction guard | A separately approved attempt cap (initial 16; 20 only when the user approves), including conservative unknown-delivery attempts | Temporary diagnostic control, not teacher requirement or NFR-01 implementation |

A reproduction checkpoint continuation must preserve its cumulative attempt history. It is external diagnostic tooling on unchanged baseline source; it does not establish production C4 checkpoint-resume compliance. Production metered resume remains disabled until restoration is implemented/tested.

## Confirmation and change policy for v1

Team review can accept this version as the common first contract. Do not reopen settled choices merely because the implementation has not yet been written. A feature owner may adapt internal class/function organization without changing these record names, field types, authority or failure meanings. Public changes, source-validity changes, thresholds and shared dispatch/sink edits need an explained contract/test revision and affected-owner review. Exact file approvals and each feature's independent test approval still occur before its implementation.
