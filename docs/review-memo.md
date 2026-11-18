# PR review memo

Add one dated entry per PR. Link pre-code plan/test approval and the actual results for the revision under review. Keep the memo free of credentials, student identifiers and raw session text.

| Required review area | What to record |
| --- | --- |
| Scope and spec | PR link, revision, reviewer, D1 IDs, requested versus actual behavior and fit criteria |
| Architecture | Owner module, ADR/invariants, integration boundaries and any changes to permissions, configuration or public API |
| Code and tests | Correctness, normal and negative cases, regression outcome, uncovered cases and residual risk |
| Security and efficiency | Untrusted model/data handling, traversal and secret exposure, authority bypasses, duplicate calls, output size or unjustified dependencies as relevant |
| Operations | Pre-code approval link and time; check commands and results; AI-use/session reference; runtime fallback, monitoring and rollback |
| Decision | Findings with owner or follow-up and one verdict: APPROVE, CHANGES REQUIRED, or REJECT |

## Entry template (copy for each actual PR)

- **PR / revision / date / reviewer:**
- **Requirements and invariants:**
- **Plan and tests approved before implementation:** reviewer, timestamp, and reviewed plan/test reference
- **Spec and architecture findings:**
- **Code and test findings:**
- **Security and efficiency findings:**
- **Operational metadata and evidence:** checks with pass/fail/not run; rollout/fallback; AI-use reference
- **Open findings and required action:**
- **Verdict:** APPROVE / CHANGES REQUIRED / REJECT

## DOC-REVIEW-001 — Interface 1.0

- **PR:** https://github.com/EverForests/TradingAgents_Pro/pull/3
- **PR workflow:** Merged by EverForests into `feat/course-deliverables` on 2026-11-15; merge commit `d2fd388cef1d318ed05644d788aefc68b5d91992`. D1 retains its recorded specification status.
- **Preparation base:** `ec1cb8b2177bafdf09c86cd8f072119c487fdce8`.
- **Pre-edit reference:** `2e1bb68aff2ca48363293ca5e1bbc43970d2fab8`; the submitted editorial revision is identified by the PR head.
- **Scope:** D1–D4 and D9 documentation/schema; requirement IDs, acceptance criteria and shared interface semantics are retained.
- **Human verdict:** Not recorded.

### Source register

| ID | Source | Scope and evidence boundary |
|---|---|---|
| SRC-01 | Teacher Project Requirement Sheet, pp. 5–10; SHA256 `6af742d3cbc0973b056a084ba54ff413a5885b1bb4d6a97b0b08b93f64f2ef7e` | Deliverable structure, verification and six blocking-gate categories |
| SRC-02 | Team consolidated proposal, pp. 4–6; SHA256 `0cb42c41c3610c8c5e55e8438d98f400f2cdd183cff0569925f5eeb8778ddfbd` | Five selected requirements; final FR-03 corresponds to original REQ-TA-FR-002 |
| SRC-03 | Teammate AAPL sentiment report; SHA256 `d425e9f0eb2b4c076b555e5f0ba95f48d7714a4684a036bae2c0f55b86c54450` | Reported missing sources with Neutral/5.0; report content is distinct from raw provider evidence |
| SRC-04 | Teammate five-stock summary; SHA256 `56f72230defd62aaa56c7b93631167b51ab55b5701cd82973593e2878df2dedc` | Reported headings and 18–21 calls; complete raw request traces were not supplied |
| SRC-05 | Teacher B3.1 example; SHA256 `fe1211a3ebaeff9c15380b07e3aa920987d5aa0d6c0eb305ca3df9fd4d6b46e5` | Reference for separated roles, failure actions and evidence discipline; not an application baseline |
| SRC-06 | [FR-02 owner review](https://github.com/EverForests/TradingAgents_Pro/pull/3#issuecomment-6896458912), KyrieT331 | AAPL Cost of Revenue FY2025/FY2026 operands, USD_millions and signed gap definition; annual-statement primary return pending |
| SRC-07 | Retained baseline `get_verified_market_snapshot`, AAPL/2026-11-10; raw tool-return receipt SHA256 `fa8a4b651c5e7db3a09811e2873999f5dc4c1cad6dd9c9b0ad385b06f58a365f` | `boll_ub = 352.771`, `Close = 348.245` USD; values/date independently checked against retained tool output |

Original materials and raw sessions remain in the private course archive. Public artifacts retain sanitized references and hashes. Diagnostic attempt limits are recorded with their runs and do not define the product request budget.

### Verification record

The committed interface revision has 17 passing static documentation checks covering schema, scope, references, links and protected files. Its 28 case IDs are planned acceptance cases. The editorial revision passed 18 static checks; working-copy hashes and command evidence are retained in the private review receipt. Feature acceptance, runtime permissions and CI enforcement require their own results.

BUG-02 records the independent sentiment evidence. A separate original market-only flow completed for AAPL/2026-11-10; it did not include all analyst roles. Reference artifacts remain distinct from enhanced-system acceptance.

### Open items

| Item | Owner | Required before |
|---|---|---|
| Interface compatibility and common starting SHA | Integrator and affected feature owners | Dependent implementation |
| Exact-path permissions and actual role guard probes | Governance maintainer | Affected OpenCode task |
| Original AAPL annual-statement return and NVDA/MSFT operand provenance | FR-02 owner | Real-company acceptance |
| Tokenizer, model capacity and input-token policy validation | Context owner and integrator | Token-compliance claim |
| Six blocking gates and branch protection | CI maintainer and repository administrator | Applicable merge |
| Functional/nonfunctional count interpretation in Introduction | Team coordinator | Final scope compliance review |

### Feature review procedure

Each feature PR supplies its base SHA, interface/fixture versions, exact plan/test approval, shared-file owner, failing-before evidence and actual regression results. Review the diff against the intended integration branch. Retarget dependent PRs after their base is merged and recheck the diff. A human reviewer records APPROVE, CHANGES REQUIRED or REJECT for the reviewed revision.

## FR03-REVIEW-006 — 2026-11-17 module handoff

- **PR / revision / reviewer:** [PR #6](https://github.com/EverForests/TradingAgents_Pro/pull/6); tested application `b2816ecb4b6dc465c38bd0ff213ea215a0662825`; Codex delegated operator assessment, supported by two real read-only OpenCode reviews. This is not a student/human GitHub approval.
- **Scope:** FR-03, C0/C3 v1.0. Full requirement/code/test map, exact commands, report section and integration checklist: [FR-03 handoff](fr03.md). Aggregate evidence: [fr03-evidence.json](fr03-evidence.json).
- **Plan/tests before implementation:** reviewed requests, frozen hashes and actual red cases are retained privately. Codex selected and approved the concrete scope under the student's general autonomy instruction. Individual student per-item approval did not occur; do not retrospectively record it.
- **Architecture:** local receipts, normalization, coverage and finalization at existing seams; no model authority over coverage; legacy return formats preserved. Shared state/schema/report changes are narrow. C1/C4 final acceptance belongs to the integrator and affected owners.
- **Code/test quality:** 47 final boundary cases, combined 1533 passing tests and 100 subtests; 39 skips (6 pre-existing platform/optional, 33 paired without a configured baseline), one integration deselection. Configured paired replay separately passed 33 assertions over 16 cases on the same final application. Ruff/YAML/diff passed. Tests and original failures were not rewritten to manufacture passes.
- **Security/efficiency:** no runtime key or raw transcript is published. Optional API collectors preserve defaults. The zero-source model path is not bound or invoked; valid neutrality remains permitted. Fake invocation reduction is 16 to 11 within the frozen synthetic diagnostic only. No billed-token or real-market performance improvement is claimed.
- **Operational evidence:** native OpenCode exports and per-run records accompany the private D5 module materials. Earlier school checks remain tied to 06d160a; no runtime API requests were added for the later deterministic fixes. Candidate CI run44090902155 succeeded. The final documentation commit has its own CI receipt through the PR.
- **Open actions before integrated release:** real human review of the current PR; final student contribution/reflection check; C0/C1/C4 integration; all applicable teacher blocking gates and branch protection. Missing historical student approvals cannot be repaired by a later signature.
- **Proposed verdict: CHANGES REQUIRED for integrated/course release readiness.** FR-03 module verification supports handoff for review; the remaining actions above do not imply an unreported module test failure. **Human final verdict: not recorded.**

## PR-NFR01-001 — Per-run model request budget (owner module)

- **PR / revision / date / reviewer:** branch `feat/nfr-01-request-budget`, base `486a9a5d74433aedd3c858c483a8d77bf0f7b897` (merge of PR #5); PR not yet opened; 2026-11-16; reviewed by JunKai Yan (NFR-01 owner acting as maintainer for this feature branch).
- **Requirements and invariants:** NFR-01 (§2.3), INV-02, contracts C0/C4, ADR-001. Owner module `tradingagents/llm_clients/request_budget.py`; offline suite `test/offline/test_request_budget.py`.
- **Plan and tests approved before implementation:** Gate 1 plan session `ses_e1cce6943ffeM6m8a640UGrQql` approved 2026-11-16 15:12 with decisions D-NFR01-01..08; test revision approved 2026-11-16 15:19 after the human-run red baseline (`37 failed, 1 passed`) was recorded; implementation authorised at 15:20. The two false-passing assertions were narrowed under D-NFR01-01 before implementation, not after.
- **Spec and architecture findings:** the module implements C4 exactly (atomic reserve, charge at the attempt boundary, one send, typed refusals, unknown-delivery accounting, no reset/restore API, no unmetered mode) and cites Requirement NFR-01, Invariant INV-02, Contract C4 and ADR-001 in its docstring. Two deliberate deviations from a full delivery remain: the gate is not wired into the graph and nothing maps its failures to the C0 terminal state (TD-10); `ContextTooLarge` is owned by this module although the context reduction itself belongs to C5/NFR-02, so the integrator must not import a second competing class.
- **Code and test findings:** 38 offline tests cover T-NFR01-BOUNDARY (17 case references), T-NFR01-RETRY (5), T-NFR01-ISOLATION (6), T-NFR01-FAILURE (11), T-NFR01-RESUME (6) and T-INV02-RACE (4). Assertions count real fake-transport sends rather than the module's own counters. Review corrections: D-NFR01-05 fixed a race assertion that demanded a delivery confirmation the primitive path never emits; D-NFR01-06 fixed SIM105/UP035; D-NFR01-07 removed the reserved decision word "hold" from module prose; D-NFR01-08 added the ADR citation. No production defect was found by review.
- **Security and efficiency findings:** standard library only, no new packages, no network calls, no logging of payload content, no secrets in code or tests. State transitions and snapshots are guarded by a single `threading.Lock`; there is no global mutable state, so concurrent runs cannot share counters. The module refuses before an over-limit send instead of retrying, and an ambiguous provider error keeps the slot charged.
- **Operational metadata and evidence:** `pytest -q test/offline` → 38 passed; `pytest -q tests test/offline` → 1450 passed, 1 skipped (langchain_aws absent), 1 deselected; `ruff check .` → clean; `git diff --check` → clean; 38 cases collected; Python 3.11.18, pytest 9.2.0, ruff 0.17.5, OpenCode 2.3.0. Red baseline before implementation: 37 failed, 1 passed (the pass is the static source guard, expected green both sides). Mutation evidence: raising the capacity bound produced 8 failures including both T-INV02-RACE tests; neutralising `cancel_before_send` produced 3 failures; removing delivery confirmation produced 1 failure; the temporary plugins lived outside the repository and were deleted. Rollback is removing the two added files; no baseline file is modified.
- **Open findings and required action:** TD-09 default `testpaths` does not collect `test/offline`; TD-10 graph wiring and C0 terminal mapping; TD-11 SDK/transport retry configuration unverified in the real client; TD-12 settlement exclusion is a static source check, not behavioural; TD-13 the module duck-types `PreparedRequest` instead of validating the C5 record; TD-14 resume disabled is the accepted v1 policy. The independent verify session (`ses_e1cc3cde9ffev4PHpzLJ9n611D`) returned "conditionally compliant" and explicitly refused to sign off "NFR-01 is delivered", "no official rating on refusal" and "no implicit retries" as end-to-end claims.
- **Verdict:** APPROVE for the owner-module revision (two files). This is not a delivery sign-off for NFR-01; the integration items above are tracked in the debt register and must be closed by the integrator before the feature is claimed as enforced.

## PR-NFR01-002 - Re-baseline re-verification of the per-run model request budget

- **PR / revision / date / reviewer:** branch `feat/nfr-01-request-budget`, base `3d5ce620e7da497e09c986ef6cbc957b490de632` (contains `1a54b9c`, the allowlist fix requested by a teammate); PR not yet opened; 2026-11-16; reviewed by JunKai Yan (NFR-01 owner acting as maintainer for this feature branch).
- **Why this entry exists, and what it does not do:** PR-NFR01-001 was measured on `486a9a5` with 38 tests and the coarse mutation counts 8/3/1. It is kept unchanged as the dated record of that revision. Moving the branch to `3d5ce62` changed one docstring line and added one test, so this entry records the results for the tree that will actually be reviewed, and does not restate the old numbers as current.
- **Session reconciliation (raised by Gate 4 as an integrity issue):** the two ID sets belong to two different rounds and are both real, not duplicates of one gate. Round 1 on `486a9a5`: plan `ses_e1cce6943ffeM6m8a640UGrQql`, verify `ses_e1cc3cde9ffev4PHpzLJ9n611D`. Round 2 on `3d5ce62`: plan `ses_e1cb0bce4ffeSMiYzgvWzPty3y`, build `ses_e1caf1566ffeefvZW8dDBgx8mJ`, verify `ses_e1cab4f89ffed8ePmZwWo5Ljy0`. All five IDs resolve in the local session store (`session_v2`, OpenCode 2.3.0).
- **Why the gate was re-run at all:** the round-1 plan session could not read `docs/README.md` and `docs/review-memo.md`; the permission allowlist omitted them while `Prompt.md` line 37 made them mandatory pre-planning reading, so the human supplied their content out of band. `1a54b9c` adds those two paths plus `docs/req/product.yaml`. The round-2 plan session is the evidence that the fix works: it read twelve required documents with its own tool and reported no denial.
- **Plan and test revision approved before the change:** plan and E-3 approved 2026-11-16 15:52 with D-NFR01-09..15. D-NFR01-09 required the appended dispatch-level race test to be recorded as a coverage addition, not a defect fix, because the implementation was already correct at that boundary.
- **Code and test findings:** one docstring line changed (`revision 486a9a5.` -> `Contract C4 v1.0 (interface-v1.0).`), and one test appended at lines 741-806; lines 1-740 are untouched. The appended test drives `dispatch` from two barrier-synchronised threads for the last slot and asserts one send, one typed refusal, `charged_attempts == LIMIT`, `known_sends == LIMIT` and `transport.send_count == LIMIT`.
- **Operational metadata and evidence:** 39 passed, 39 collected; `ruff check` clean on both files; repository regression 1412 passed, 1 skipped, 1 deselected; `git diff --check` clean; Python 3.11.18, pytest 9.2.0, OpenCode 2.3.0, model `cityucs/CS5351/DeepSeek-V4-Flash`. Mutation results M1 13 / M2 2 / M3p 5 / M4 2 with the exact substitutions listed in the trace matrix; each run restored the module and ended green.
- **Security and efficiency findings:** unchanged from PR-NFR01-001 (standard library only, no network, single lock, no global state). The one new test adds threads and a barrier but no sleeps and no wall-clock dependence.
- **Open findings and required action:** TD-09 (CI does not collect `test/offline`), TD-10 (no production importer, no C0 terminal mapping), TD-11 (SDK retry configuration unverified), TD-12 (static settlement check), TD-13 (duck-typed prepared request), TD-15 (Verify role cannot read the evidence records, so record integrity is human-reviewed), TD-16 (no guard that a `run_id` is instantiated once, so two `RequestBudget` objects with the same id could each spend the full limit).
- **Verdict:** APPROVE for the owner-module revision at `3d5ce62` (two files, one docstring line and one appended test). CONDITIONALLY COMPLIANT for the owner module; not a delivery sign-off for NFR-01. The six missing items named by Gate 4 remain: integrator wiring for both tiers, C0 terminal-state mapping, verified SDK retry configuration, CI collection of `test/offline`, behavioural settlement-exclusion evidence, and read access (or human review) for the evidence records.

## FR-01 / INV-01 — Post-implementation review draft (2026-11-16)

- **PR / reviewed revision:** [PR #4](https://github.com/EverForests/TradingAgents_Pro/pull/4); local revision `712617e25a380197e38d6ee5cc4dcc7ab393cf61`. The test evidence below is for this revision, not necessarily the current remote PR head.
- **Comparison base / specification:** `3d5ce620e7da497e09c986ef6cbc957b490de632`; D1, D4 and C0/C1 v1.0.
- **Pre-implementation approval:** Plan/test approval was not present in the material reviewed. Link the contemporaneous record if available. This review does not establish or replace prior approval.
- **Review provenance:** Read-only OpenCode review of the implementation and seven offline test files, supplemented by terminal test results. The human reviewer has not signed off.

### Verification evidence

| Area | Verified behavior and limits |
| --- | --- |
| Gate and Python API | Legal rating with valid references publishes; illegal ratings and missing, unknown or foreign IDs are rejected in the tested cases. Rejected candidates do not become official API ratings. See `test_fr01_gate_unit.py`, `test_fr01_cross_run.py`, `test_fr01_publish_valid.py` and `test_inv01_key_counterexample.py` under `test/offline/`. |
| CLI | Simulated state-stream frames do not show the candidate before approval; rejected candidates remain hidden from official display and show a blocking reason. Approved candidates appear after the gate. The test does not inject raw model messages or inspect the message log. See `test_inv01_cli_no_premature_display.py`. |
| Reports and memory | Rejected-run Markdown and HTML heading checks, no rejected decision-memory entry, and a positive memory-write control are covered. The HTML test uses no report sections; full HTML and direct `save_reports()` calls with ungated state remain unverified. See `test_inv01_four_exits.py` and `test_fr01_publish_valid.py`. |
| Checkpoint resume | An interrupted run preserves its run ID and resolves its evidence chain on resume. This does not exercise replacement with a complete index from another run. See `test_inv01_resume.py`. |

- **Offline:** `test/offline`: 26 passed. `tests test/offline`: 1438 passed, 1 skipped (optional Bedrock dependency `langchain_aws` missing), 1 deselected and 100 subtests passed. The successful full run allowed loopback port binding and bypassed the proxy for `localhost` and `127.0.0.1`.
- **Diff check:** `git diff --check 3d5ce62...HEAD` passed at the reviewed revision. **Live tests:** not run.
- **Upstream tests:** Five upstream files changed, so the full-suite result is for the current branch. The original diffs of `tests/test_cli_memory_log.py`, `tests/test_debate_opening.py`, `tests/test_graph_end_to_end.py` and `tests/test_memory_log.py` remain for human review; the agent saw summaries only. Confirm that the revised expectations preserve relevant regression assertions and identify the approval record for intentional behavior changes.

### Findings and follow-up

| When | Finding and evidence needed |
| --- | --- |
| Before FR-01 sign-off | C0/C1 shared record fields and callable interfaces differ from the implementation. In particular, the evidence record lacks required run identity and source locators, the result does not expose the required reference lists, and the gate entry points do not expose the specified signatures. Check that accepted claims are nonempty. The FR-01 owner and integrator should agree on a conforming adapter or a reviewed contract revision. |
| Before FR-01 sign-off | Reproduce direct `save_reports()` with ungated state and complete HTML output, and a run using a whole evidence index from a different run. Document actual outcomes and add approved tests for the agreed boundaries. Normal resume and normal report output do not cover these cases. |
| Before FR-01 sign-off | Decide whether raw CLI model messages and logs are private diagnostics or part of official output; verify the agreed boundary with a nonempty candidate message. The stale progress-field lookup does not by itself establish a rating leak. |
| During integration | Verify that budget exhaustion and context rejection suppress publication even with otherwise valid candidate evidence, and that FR-03 `NO_DATA` diagnostics cannot serve as substantive evidence. Record results against the integrated SHA. |

- **Suggested verdict:** **CHANGES REQUIRED** pending contract alignment or a reviewed revision, evidence for the open FR-01 paths, and human review of the upstream test changes and approval record. This is an advisory draft, not a merge approval.

## Feature PR intake — 2026-11-18

The coordinator accepted the five heads below for **local integration**. That decision is not a GitHub Review, a substitute for pre-implementation approval, or approval to merge into `main`. GitHub returned no submitted Reviews for these PRs at intake. Each head had six successful GitHub checks (four Python test jobs, install smoke and Ruff); those results do not verify the combined tree or all course blocking gates. Local test totals below are **PR-author reports**, not reruns on the combined tree. PR #9 was superseded by #10 and is not an integration input.

### FR-01 / INV-01 — [PR #4](https://github.com/EverForests/TradingAgents_Pro/pull/4)

- **Head:** `a5b987256fdf52ad60c254d451b9df5b0aa817a3`. This intake record covers a newer head than the earlier review draft; it does not overwrite that draft.
- **Scope and evidence:** C0/C1 retained market snapshots, run-local argument validation and a shared publication result across CLI, API, reports and memory. The PR reports reproducing a foreign-index bypass and ungated report save before the repair. It reports 62 contract cases and 109 course offline cases passing at `7aa478b`; those counts are not attributed to the later head. Live acceptance not run in that report.
- **Approval and follow-up:** Author reports review of R8-B and the boundary repair; approver, timestamps and supporting links remain placeholders. Verify terminal states suppress publication, and `NO_DATA` diagnostics cannot become evidence in the combined graph.

### FR-02 — [PR #8](https://github.com/EverForests/TradingAgents_Pro/pull/8)

- **Head:** `51c52268bb9b8d59663fbfc27d156a50e39809d4`. C0/C2 verified YoY, ratios and signed price differences from current-run source operands; Portfolio Manager and report resolve issued IDs, not model-provided numbers.
- **Evidence:** Author reports 48 feature cases and 1460 combined local passes (1 skipped, 1 deselected), plus Ruff. Tests exercise normal completion and analyst wrap-up, invalid provenance and foreign IDs. Original NVDA tool reply was unavailable; its frozen case has retained SEC cache/report provenance.
- **Approval and follow-up:** Author cites `FR02-PLAN-01` and maintainer approval on 2026-11-16; underlying records are private and not independently checked here. Preserve market evidence collection and verified-metric registration in the same analyst graph. Render results without granting publication authority to the numeric registry.

### FR-03 — [PR #6](https://github.com/EverForests/TradingAgents_Pro/pull/6)

- **Head:** `4c4574242f763d6c9883a489540d016d5ed397a9`. C0/C3 request-bound sentiment receipts and explicit coverage. Zero valid sources produce `NO_DATA / UNKNOWN / null` with zero sentiment model calls; measured neutral remains possible with valid inputs.
- **Evidence:** Author reports 47 boundary checks and 1533 combined local passes at application revision `b2816ec` (39 skipped, 1 deselected). A separately enabled paired diagnostic reported 33 passing assertions. School-model checks were reported separately at `06d160a` using synthetic receipts; these are not live acceptance of the combined project.
- **Approval and follow-up:** The PR explicitly reports no individual student plan/test review or final human verdict during feature development. Verify C1/C4 behavior in the combined graph; missing sentiment must not inflate evidence or consume a sentiment-model slot.

### NFR-01 / INV-02 — [PR #7](https://github.com/EverForests/TradingAgents_Pro/pull/7)

- **Head:** `e47760cfdeffde99d7279147e061927525d08a12`. C4 owner module implements atomic reservation/charge/cancellation and fake outbound dispatch tests.
- **Evidence:** Author reports 39 acceptance cases, 1412 repository regression passes and four mutation runs that failed as expected; the restored tests were reported green.
- **Approval and follow-up:** PR cites human decisions `D-NFR01-09..15` and conditional owner-module approval. It explicitly has no production caller; verify actual dispatch on both tiers, fallback/retries, C0 terminal mapping, last-slot concurrency and metered checkpoint policy before delivery sign-off.

### NFR-02 — [PR #10](https://github.com/EverForests/TradingAgents_Pro/pull/10)

- **Head:** `e24e7d88e8056a10e02bfd7b604ae91d3c1b1c61`. C5 canonical UTF-8 byte accounting and deterministic reduction at Analyst Wrap-up and Neutral Risk Debater; only older optional groups can be removed.
- **Evidence:** Author reports 37 feature cases and 1449 regression passes (1 skipped, 1 deselected). A separate fake-model demonstration reported zero invocations for irreducible input; no live-provider acceptance.
- **Approval and follow-up:** The PR describes human approval of edits and read-only verification; exact approval receipts are not linked here. Integrate C0 error mapping and prove context rejection occurs before C4 reservation, debit or send. Verify the prepared message representation at the provider boundary.

### Combined-tree review — Local integration, 2026-11-18

The coordinator approved the local integration work in the project chat on
2026-11-18. The branch started at `486a9a5`, incorporated shared permission
maintenance through `5f40d21`, and included all five reviewed parents by
`208f828`. The order was #4, #10, #8, #6, #7. The intake table preserves the
approval evidence available for each contributor. Today's coordinator approval
applies to integration.

| Integration area | Observed before and evidence after repair |
| --- | --- |
| C0/C1/C2 | The initial combined #8 run failed because the FR-02 initialization reminted the run ID and several assertions still expected Portfolio Manager to publish. The repaired graph keeps one shared identity, both verified-metric producers, retained market evidence and candidate-only manager output. The existing numeric assertions remained in place. The FR-01 and FR-02 targeted run passed 110 cases. |
| C1/C3 | The real market-plus-social graph exposed that the sentiment node produced a record that the subgraph dropped. The positive joint case now checks NO_DATA/null and no sentiment-model binding while an approved market-evidence rating still resolves. Five downstream prompt assertions cover both structured research and plain risk requests. |
| C0/C4 | At a limit of three, the SDK transport fixture observed four sends before integration. The repaired runner allows all three requested attempts to finish, refuses attempt four and suppresses the official rating and decision-memory write. The suite also exercises parallel graph workers, a second run's fresh budget, streamed execution, and provider transport failure with SDK retries off. Historical settlement runs outside this ledger. Metered checkpointing is refused. |
| C0/C4/C5 | The neutral-risk integration fixture injects irreducible required content and checks zero reservations and zero provider sends. The two scoped sites keep deterministic reduction, with a final check on the provider message array in the metered profile before C4 dispatch. |
| CityU request shape | The final fake SDK transport check first observed a missing `thinking` key. After the profile repair, both tiers send the approved alias and `thinking: {type: disabled}` to the configured CityU host, with SDK retries forced to zero. |

OpenCode generated the application changes and the initial transport fixture.
Codex maintained Git, fixture adaptations, test commands and CI. The legacy
memory regression keeps its original approved-write assertion and binds the new
real methods on its graph stand-in. See AI-use entry
`AI-COURSE-INTEGRATION-20261118` for sessions and scope.

The workflow runs the upstream and course offline suites, the fixed FR-03
paired comparison, lint, dependency consistency and install smoke checks,
requirements schema and reference validation, OpenCode permission-copy parity,
and a new AI-use record check on application or prompt PRs. The paired diagnostic
uses synthetic facts. Full D7 semantic acceptance, formal historical approval
receipts, GitHub required-check enforcement and independent hosted CI are separate
open evidence items. No live application analysis was run during integration.

**Local verification of `cb5d52f805329f2452c1423dec29ee835acfeab8`.**

- Python 3.13.3, `python -m pytest -q tests test/offline`, with
  `FR03_BASELINE_ROOT` at pinned upstream `9fa1196` and loopback proxy
  bypass. **1812 passed, 1 skipped, 1 deselected, 100 subtests passed.**
  The skip was the missing optional Bedrock dependency. The deselected
  test requires the real DeepSeek API. The 33 paired FR-03 checks ran.
- Ruff, baseline-to-head diff whitespace, schema/reference, AI-use log and
  permission-copy checks passed. Clean package installation in a fresh
  environment passed `pip check` and imports of `tradingagents` and `cli.main`.
- The coordinator can now run online acceptance on the local integration
  branch using the [CityU profile](../README.md#integrated-course-run).
  Hosted GitHub Actions and branch protection remain to be verified.

**Hosted CI follow-up.** The first push exposed a workflow startup error because
GitHub treats `NO_PROXY` and `no_proxy` as the same YAML environment key. CI
now exports the lowercase variable inside the test step. The PR artifact check
also handles adding the first AI-use log to `main`. The next workflow ran its
jobs, with the artifact, Ruff and clean-install jobs passing. A separate fresh
local install reproduced two FR-02 Bollinger-band failures with
`stockstats 0.6.14`, whose implementation uses population standard deviation.
The dependency now resolves to `0.6.13`, preserving the approved sample
standard-deviation calculation. The default suite in the fresh environment
then ran with 1779 passed, 34 skipped (the 33 paired cases and optional
Bedrock), 1 deselected and 100 passing subtests.
