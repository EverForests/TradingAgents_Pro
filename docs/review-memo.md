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

- **PR / revision / review evidence:** [PR #6](https://github.com/EverForests/TradingAgents_Pro/pull/6), tested application `b2816ecb4b6dc465c38bd0ff213ea215a0662825`. Local test results and two read-only OpenCode Verify reviews support the module assessment. The [AI-use log](ai-use-log.yaml) records the review and terminal activity. The team verdict remains with the delivery review.
- **Scope:** FR-03, C0/C3 v1.0. Full requirement/code/test map, exact commands, report section and integration checklist: [FR-03 handoff](fr03.md). Aggregate evidence: [fr03-evidence.json](fr03-evidence.json).
- **Plan and test evidence:** Private records retain plan requests, frozen test hashes and the failing zero-source check. The original node called the model once where the test expected zero. The [AI-use log](ai-use-log.yaml) records plan review and terminal execution. Wang Mingqian reviewed the concrete plan and tests before implementation.
- **Architecture:** local receipts, normalization, coverage and finalization at existing seams; no model authority over coverage; legacy return formats preserved. Shared state/schema/report changes are narrow. C1/C4 final acceptance belongs to the integrator and affected owners.
- **Code/test quality:** 47 final boundary cases, combined 1533 passing tests and 100 subtests; 39 skips (6 pre-existing platform/optional, 33 paired without a configured baseline), one integration deselection. Configured paired replay separately passed 33 assertions over 16 cases on the same final application. Ruff/YAML/diff passed. Tests and original failures were not rewritten to manufacture passes.
- **Security/efficiency:** no runtime key or raw transcript is published. Optional API collectors preserve defaults. The zero-source model path is not bound or invoked; valid neutrality remains permitted. Fake invocation reduction is 16 to 11 within the frozen synthetic diagnostic only. No billed-token or real-market performance improvement is claimed.
- **Operational evidence:** native OpenCode exports and per-run records accompany the private D5 module materials. Earlier school checks remain tied to 06d160a; no runtime API requests were added for the later deterministic fixes. Candidate CI run44090902155 succeeded. The final documentation commit has its own CI receipt through the PR.
- **Open actions before integrated release:** Review the current PR and record the team verdict, confirm the final contribution record and reflection, verify C0/C1/C4 integration, and check the applicable course gates and branch protection.
- **Proposed verdict: CHANGES REQUIRED for integrated/course release readiness.** FR-03 module verification supports handoff for review; the remaining actions above do not imply an unreported module test failure. **Human final verdict: not recorded.**
