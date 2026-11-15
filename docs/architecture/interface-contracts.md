# Shared interface contracts

Status: **proposed predevelopment-v1**. These are semantic contracts to review before implementation, not classes or modules already present. Preserve the five D1 requirements. Implementers may choose dataclasses, TypedDict or existing Pydantic models after the affected owners approve one representation. Do not create parallel representations with different meanings. ADR-001 governs these choices.

## Ownership and integration

| Contract | Authority | Producers and consumers |
| --- | --- | --- |
| C0 run identity and outcome | Run coordinator | All five owner modules, CLI, Python, report and memory |
| C1 evidence and publication | FR-01 publication gate | Analyst evidence, accepted arguments, candidate, all official sinks |
| C2 verified metrics | FR-02 metric registry | Fundamentals inputs, controlled downstream fields and metric table |
| C3 sentiment coverage | FR-03 coverage component | Existing source adapters, analyst, state, report and downstream agents |
| C4 dispatch budget | NFR-01 request-budget component | Both model tiers and every in-scope transport send |
| C5 prepared context | NFR-02 context component | Analyst closure and neutral risk debater, then C4 |

Shared-file edits (`agents/state.py`, `agents/schemas.py`, graph/client adapters and reporting) need an integration owner agreed by the team. Feature owners propose narrow patches; the coordinator preserves all approved contracts when combining them. Contract IDs are stable; exact function signatures and the shared-file owner must be frozen in the approved task plan.

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

FR-02 adds verified numerical records; FR-01 must not label arbitrary model prose as verified arithmetic. FR-03 missingness does not automatically invalidate other evidence. Agree the exact sink adapters before implementation and test each one.

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

Missing scores never become 0 or 5 and never enter a numerical mean. Structured state, analyst message, downstream prompt and persisted/rendered report must agree. Handle nullable scores without numeric-format errors. Apply the contract to structured **and** free-text fallback; model narrative cannot override authoritative coverage. Existing report field names may be retained by extending the schema, but confirm the exact representation with all consumers before Build.

The original baseline stores `sentiment_report` as text and requires a nonnull numeric SentimentReport score. Updating only the prompt cannot establish this contract. No raw social bodies or credentials belong in public evidence. Missing optional sentiment does not stop otherwise valid market/fundamental analysis; C1 still decides publication.

## C4 — atomic per-run model dispatch

Supported scope: one single-stock main analysis, both model tiers, structured/fallback requests and application retries. Count actual outgoing model attempts, not nodes, tool invocations, callbacks or tokens. Historical settlement is excluded. Disable SDK/transport implicit retries in supported course runs; unsupported hidden-retry modes are outside the verified configuration, not silently compliant.

Budget state: positive integer `limit`, charged sends, active reservations and exhaustion. Atomically reserve capacity before a send so charged sends plus active reservations cannot exceed limit. A reservation transitions once to a charged attempt at the outbound boundary. A provider error after an attempted send consumes the slot; do not refund an ambiguous send. A cancellation proven to precede transport may release an unused reservation. Validate C5 first so context rejection obtains no reservation.

No slot => BUDGET_EXHAUSTED, no request, no official recommendation. Limit 3 allows exactly 3 attempts; the fourth is refused. Concurrent runs do not share counters. Include application fallback/retry attempts separately. C4 does not promise a monetary or token cap. Transport probes must count actual fake sends and check reservation cleanup rather than trusting the reported counter alone.

## C5 — deterministic prepared context

Initial integration sites: analyst closure and `risk_mgmt/neutral_debator.py` only. Other analyst turns and risk roles are not implicitly covered. Before reserving C4, fully expand/convert the scoped final message sequence into one agreed provider-facing representation.

Proposed canonical measurement: a JSON array of message objects with deterministic field/key order, UTF-8 encoding, non-ASCII preserved, compact separators (no optional whitespace), and nonfinite numbers rejected. The owner plan must state the exact normalization of role, content, tool-call IDs/name/arguments and tool results, and freeze byte fixtures from that representation. Do not measure before template expansion or change representation after measuring. Tool schemas and other separately bound fields are excluded from this message metric and must be recorded/bounded separately; this is not a cap on the whole HTTP body.

Required blocks: role/task identity; standing safety/publication rules; ticker/date/run identity; current required evidence/verified metrics/source coverage; and the active tool-call/result exchange. Optional blocks: explicitly marked older discussion/history. A tool-call/result pair is indivisible; if a member is required, preserve the whole pair. Text-wrapped tools retain name, arguments and corresponding result. Removing context cannot delete authoritative evidence/state from storage.

At the proposed 65536-byte test cap: short input passes unchanged. If oversized, remove optional groups oldest first (stable original index for ties), reassemble, reinject critical constraints and remeasure. Do not summarize required evidence with another unmetered model call. If required blocks cannot fit or pairing cannot be preserved, return CONTEXT_TOO_LARGE; zero send, reservation and debit. Same normalized input/config produces identical prepared output. Run final retention/pairing checks before C4.

This byte cap does not implement the separate D2 token-budget requirement. ADR-001 records that architecture design and the remaining tokenizer/model-capacity validation. Do not infer token counts from bytes/4 or claim provider safety from 64 KiB alone.

## Contract-change and approval record

Before implementation, record requirement IDs, contract revision, baseline SHA, exact read/edit paths, fixture/case revision, reviewer and approval time. Approval is a human decision about that revision, not an agent summary or a default assent. Document-only preparation may propose contracts; it does not approve feature implementation. Reapprove changes to shared fields, thresholds, test expectations, safety paths or dependencies. Feature PRs link the approved plan and actual evidence; the coordinator runs integrated regressions before release.
