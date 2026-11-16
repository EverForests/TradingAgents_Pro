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
