# Requirement trace matrix

Proposed owner paths and evidence. Case IDs are defined in [verification constraints](../code-governance/verification-constraints.md) and D1; none imply executable tests or pass results. Shared contracts: [C0–C5](interface-contracts.md).

| Requirement | Enforcer / integration | Planned case IDs | Runtime monitor and failure |
| --- | --- | --- | --- |
| FR-01 | C1 `graph/publication_gate.py`, analyst/argument references and four official sinks | T-FR01-VALID/RATING/MISSING/REFERENCE/SINKS (expanded full IDs in D1) | publication_status, reason codes, accepted references; BLOCKED if rejected |
| FR-02 | C2 `agents/verified_metrics.py`, fundamentals/state/report | T-FR02-YOY/RATIO/DELTA/INVALID/IDENTITY | verified/unverifiable counts and reason codes; invalid records excluded |
| FR-03 | C3 `agents/sentiment_coverage.py`, sentiment/schema/state/report/downstream | T-FR03-COVERAGE/INVALID/NEUTRAL/PROPAGATION/SCORE | valid logical sources, per-source reasons, coverage and nullable assessment; optional data failure does not stop other valid analysis |
| NFR-01 | C4 `llm_clients/request_budget.py`, both-tier outbound path including fallback/retries | T-NFR01-BOUNDARY/RETRY/ISOLATION/FAILURE/RESUME | reservations, charged attempts, limit/exhaustion; refuse before over-limit send |
| NFR-02 | C5 `llm_clients/context_limit.py`, analyst closure and neutral debater then C4 | T-NFR02-SHORT/REDUCE/REJECT/UTF8/PAIRING/ORDER | final bytes, required-block retention, reduction count; CONTEXT_TOO_LARGE before reservation |
| INV-01 | C1 before CLI/API/report/memory, no free-text bypass | T-INV01-BYPASS, T-FR01-SINKS | rejected candidate release/persistence count must be zero; suppress/quarantine on breach |
| INV-02 | C4 atomic run-local budget and actual fake transport boundary | T-INV02-RACE, T-NFR01-BOUNDARY | actual outgoing requests above limit must be zero; refuse dispatch and publication |

Paths above are relative to `tradingagents/` except CLI adapters. Exact test filenames and shared adapter edits are frozen in each approved task plan. Requirement owners supply evidence for their feature; the integrator supplies a new receipt for combined components, not a copy of individual PR results.

## Implemented FR-03 evidence — 2026-11-17

The FR-03 row above now has an implemented mapping and recorded results in [the module handoff](../fr03.md#requirement-to-implementation-to-evidence-map) and [derived evidence](../fr03-evidence.json): COVERAGE / INVALID / NEUTRAL / PROPAGATION / SCORE all have concrete tests. Tested application b2816ec: 1533 regression passes, 100 subtests, 47 boundary controls and a separate configured 33-assertion paired replay. This is not evidence for other requirements, final publication/dispatch invariants or real-provider quality. The other proposed rows retain their owners' review states.

## NFR-01 evidence (2026-11-16, base 486a9a5 - superseded by the 3d5ce62 re-verification below)

| Item | Record |
| --- | --- |
| Owner module | `tradingagents/llm_clients/request_budget.py` (new, 253 lines, standard library only, docstring cites NFR-01 / INV-02 / C4 / ADR-001, revision 486a9a5) |
| Offline suite | `test/offline/test_request_budget.py` (38 tests, 38 collected; runtime 0.05 s; no network, no sleeps) |
| Case mapping | T-NFR01-BOUNDARY: limit 3 → 3 sends then typed refusal, invalid configuration, C5-first zero-debit, last-slot readiness (17 references); T-NFR01-RETRY: application retry counted as a separate charged attempt (5); T-NFR01-ISOLATION: two concurrent budgets, reservation occupying headroom, no settled coupling (6); T-NFR01-FAILURE: ambiguous provider error stays charged, cancellation semantics, no refund path (11); T-NFR01-RESUME: new run starts at zero, no reset/restore/refill API, resume disabled (6); T-INV02-RACE: synchronized last-slot race and 8-way concurrent dispatch, fake-send counts (4) |
| Human-run evidence | Pre-change 37 failed / 1 passed (the pass is the static source guard); post-change 38 passed; regression `tests` + `test/offline` 1450 passed, 1 skipped, 1 deselected; `ruff check .` clean; `git diff --check` clean |
| Negative controls | Mutation 1 (capacity bound raised): 8 failed including both T-INV02-RACE tests; mutation 2 (`cancel_before_send` neutralised): 3 failed; mutation 3 (delivery confirmation removed): 1 failed. Plugins were external to the repository and deleted; each mutation was followed by a green run |
| Invariant coverage | INV-02 is exercised by T-INV02-RACE at the actual fake-transport boundary; `charged_attempts == known_sends + unknown_delivery` and `charged_attempts + active_reservations <= limit` are asserted on every snapshot read |
| Ownership split | The pre-debit half of the C5 rejection path (zero reservation, zero charge on CONTEXT_TOO_LARGE) is exercised here under T-NFR01-BOUNDARY; the reduction itself remains NFR-02's T-NFR02-REJECT |
| Integration status | Not connected: no non-test module imports the gate; C0 terminal mapping, two-tier routing and SDK retry configuration remain with the integrator (TD-10, TD-11) |
| Reviewer verdict | course-verify `ses_e1cc3cde9ffev4PHpzLJ9n611D`: conditionally compliant; owner-module revision APPROVED in PR-NFR01-001, not a delivery sign-off |

Case IDs above are traced to executable tests in this revision; the earlier "planned" status of the NFR-01 row is superseded for the offline tier only. Integrated evidence still requires an integrator receipt, as stated in the trace-matrix preamble.

## NFR-01 evidence re-verification (2026-11-16, base 3d5ce62)

| Item | Record |
| --- | --- |
| Baseline | `3d5ce620e7da497e09c986ef6cbc957b490de632` ("allow reading the D1 product scope"), which contains `1a54b9c` adding read access for `docs/README.md`, `docs/review-memo.md` and `docs/req/product.yaml`. `git diff --name-status 486a9a5 3d5ce62` lists only `.opencode/opencode.jsonc`, `.opencode/permissions.jsonc` and `docs/architecture/permission-model.md`, so no code, contract, fixture or requirement text moved between the two baselines. |
| Owner module | `tradingagents/llm_clients/request_budget.py` (new, 260 lines, standard library only, docstring cites NFR-01 / INV-02 / C4 / ADR-001, revision label `Contract C4 v1.0 (interface-v1.0)` instead of a bare SHA) |
| Offline suite | `test/offline/test_request_budget.py` (806 lines, 39 tests, 39 collected; no network, no sleeps) |
| Case mapping | T-NFR01-BOUNDARY 17 references; T-NFR01-RETRY 5; T-NFR01-ISOLATION 6; T-NFR01-FAILURE 11; T-NFR01-RESUME 6; T-INV02-RACE 5, now including the dispatch-level last-slot race `test_t_inv02_race_dispatch_two_contenders_last_slot_once` (lines 741-806) |
| Human-run evidence (3d5ce62) | `.venv/bin/python -m pytest test/offline/test_request_budget.py -q` -> 39 passed; `ruff check` on both files -> clean; `.venv/bin/python -m pytest -q` -> 1412 passed, 1 skipped (langchain_aws absent), 1 deselected; `git diff --check` -> clean |
| Negative controls (3d5ce62) | M1 capacity guard in `try_reserve` replaced by `if False:` -> 13 failed; M2 `self._active_reservations -= 1` removed from `cancel_before_send` -> 2 failed; M3p `budget._mark_delivered(ticket)` in `dispatch` replaced by `pass` -> 5 failed; M4 `with self._lock:` in `try_reserve` replaced by `if True:` -> 2 failed. The coarser mutations measured on 486a9a5 gave 8 / 3 / 1; the divergent counts are expected because the mutation set is finer and one case was added, and both sets are kept rather than reconciled by editing the old numbers. |
| Gate records | Gate 1 `ses_e1cb0bce4ffeSMiYzgvWzPty3y` (course-plan, read all twelve required documents itself, no denied read); Gate 2/3 `ses_e1caf1566ffeefvZW8dDBgx8mJ` (course-build, docstring line plus one appended test only); Gate 4 `ses_e1cab4f89ffed8ePmZwWo5Ljy0` (course-verify, read-only) |
| Reviewer verdict | course-verify `ses_e1cab4f89ffed8ePmZwWo5Ljy0`: CONDITIONALLY COMPLIANT for the owner module, not compliant for NFR-01 delivery. See PR-NFR01-002 |
| Record-integrity limit | Gate 4 was denied read on `docs/ai-use-log.yaml`, `docs/bug-diary.md`, `docs/debt-register.md`, `transcripts/nfr-01-request-budget.md` and `Report.md`, reported the denial instead of bypassing it, and those five files were reviewed by the human owner instead (TD-15) |
| Integration status | Unchanged: no non-test module imports the gate; C0 terminal mapping, two-tier routing and SDK retry configuration remain with the integrator (TD-10, TD-11, TD-16) |

## Combined acceptance

The integrated `e6b6056` run records executable evidence for all five requirements, including shared C1/C4/C5 behavior and the two-tier dispatch path. See [the integrated acceptance record](../review-memo.md#integrated-acceptance-of-five-requirements--18-november-2026) for test counts, evidence limits and the CityU run procedure. The tables above record their stated historical revisions.

## FR-01 reference adapter — 19 November 2026

The invocation-local E/A selection adapter is covered by `test/offline/test_fr01_reference_aliases.py`. Its 17 real-node cases have a pre-change 12-failure/5-pass receipt. Three additional helper cases cover opaque-ID collisions and later selections. All 20 pass after repair. Full regression recorded 1,832 passes and 100 passing subtests. A real DeepSeek replay with an explicitly synthetic source selected E1 and A1/A2 and resolved the canonical chain. The fresh Yahoo checks remained rate limited. See the [follow-up review](../review-memo.md#fr-01-reference-reliability-follow-up--19-november-2026).

## Live evidence for FR-01 and FR-02 (19 November 2026)

| Requirement | What the five-company CLI run showed on `df8a9d6` | Evidence |
| --- | --- | --- |
| FR-01 | All five runs ended `COMPLETED / APPROVED` and wrote an official recommendation to both Markdown and HTML. | [Publication results by company](../live-acceptance.md#five-company-cli-rerun-on-19-november-2026) |
| FR-02 | Each official report included a Verified Metrics table. The live check covered export to the report; the offline suite checks the formulas, units, signs and rejection of invalid operands. | [Exported metric counts](../live-acceptance.md#five-company-cli-rerun-on-19-november-2026); [FR-02 offline tests](../../test/offline/test_verified_metrics.py) |
