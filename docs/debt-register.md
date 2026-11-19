# Technical debt register

The initial entries are review candidates from the design. Confirm exposure and ownership during implementation; these are not verified defects or completed work. Use statuses Candidate, Open, Accepted, and Resolved. Add concrete evidence, owner and resolution criteria before formally accepting or closing an item.

| ID | AI-era category | Related requirements | Candidate debt and next check |
| --- | --- | --- | --- |
| TD-01 | Prompt rot | FR-01, FR-03, NFR-02 | Prompt revisions could lose citation, missingness or context instructions. Check against the fixed semantic fixtures after a version change. |
| TD-02 | Hallucinated dependencies | NFR-01, NFR-02 | Generated code may assume unsupported provider hooks. Verify against the pinned dependency or supported provider; require approval for new packages. |
| TD-03 | Untouchable code | FR-01, NFR-01 | Shared graph/dispatch adapters may become hard to change safely. Keep the integration small and add boundary tests before widening scope. |
| TD-04 | Hidden dependencies | NFR-01, NFR-02 | Provider retries, checkpoint state or serialization can invalidate measurement. Document supported modes and verify sends at the transport boundary. |
| TD-05 | Agent-induced bloat | FR-01, FR-02, FR-03 | Generated adapters may duplicate checks and defaults. Review the diff against the blueprint's single-owner mapping. |
| TD-06 | Evaluation debt | FR-01, FR-02, FR-03, NFR-01, NFR-02 | Frozen operand evidence and fixed model/prompt cases must be collected before claims. Add positive/negative fixture evidence for each fit criterion. |
| TD-07 | Guardrail debt | INV-01, INV-02 | A sink or backend could bypass the gate or reservation. Test all official sinks and run concurrent negative checks before accepting the feature. |
| TD-08 | Human/cognitive debt | All | Approval rationale can disappear when work is handed over. Link the reviewed plan, tests and final verdict in each PR memo. |

For each confirmed entry add: **status**, **evidence/PR**, **impact**, **owner**, **next review trigger**, **mitigation**, and **closure proof**. Do not classify failure of a mandatory safety invariant as accepted debt; block the affected release and record a defect.

## Open verification items

- TD-06: obtain original financial operands and reproducible live configurations before accepting real-company examples; closure requires source fixtures and receipts. **FR-02 update, 19 November 2026 (open):** The [five-company CLI rerun](live-acceptance.md#five-company-cli-rerun-on-19-november-2026) records the revision, settings, market snapshots and report outputs. The archive contains SEC company-facts caches, but no raw statement replies for these runs. To close the financial-operand item, match the underlying values, units and reporting periods to the frozen cases and retain the source receipts.
- TD-07: actual OpenCode guard probes and all course CI gates remain unverified; adding prose does not close this debt. Resolve exact-path omissions before affected Build tasks.
- TD-08: five independent development sessions may drift on interfaces or claim approvals from summaries. Use one contract revision and real human review links; keep actual tool identity and shared-file ownership explicit.
- Context architecture: proposed token budget in ADR-001 still needs tokenizer/model-capacity validation; a 64 KiB message check alone cannot close it.

## FR03 module debt assessment — 2026-11-17

These statuses are FR-03-specific and do not close other owners' or global entries.

| Category | FR-03 status / evidence | Owner, mitigation and next trigger |
|---|---|---|
| TD-01 Prompt rot | Current neutral instruction covered by an independent static check; school controls at 06d160a are recorded. Global semantic CI is still open. | FR-03 owner + integrator; replay the fixed rubric on any prompt/model change. |
| TD-05 Agent-induced bloat | Paired worker remains a diagnostic with isolated imports and network blocking; no orchestration rewrite. Potential refactoring is low-priority review debt. | FR-03 owner; revisit only on a real maintenance burden, not to inflate changes. |
| TD-06 Evaluation debt | Deterministic module evidence and matched synthetic comparison verified at b2816ec; real-provider and labeled semantic quality remain open. | FR-03 owner + integrator; new data/provider or quality claims require independent frozen evidence. |
| TD-07 Guardrail debt | Real FR-03 Plan/Build/Verify capability/denial probes are retained privately. Full D7 gates and joint publication/budget acceptance remain open. | Governance maintainer and integrator; do not infer global closure from module CI. |
| TD-08 Human/cognitive debt | Actual Codex/OpenCode roles recorded. Individual student prior approvals absent; they cannot be retroactively manufactured. | Student and reviewer; perform a real current review, check personal understanding and mark contribution/reflection honestly. |

Module receipt: [FR-03](fr03.md). Full-market investment validation is outside the FR-03 missingness contract and is not presented as an implemented quality claim.

## NFR-01 debt entries (2026-11-16)

| ID | AI-era category | Related requirements | Candidate debt and next check |
| --- | --- | --- | --- |
| TD-09 | Verification debt | NFR-01, INV-02 | Default pytest `testpaths` still collects only `tests/`, so `test/offline/` acceptance cases do not run in CI. A green default run does not prove NFR-01. |
| TD-10 | Untouchable code / integration | NFR-01, INV-02 | The budget gate exists as an owner module only. No graph entry instantiates it from the run context, no model tier or fallback path calls `dispatch`, and no code maps `BudgetExhausted`/`ContextTooLarge` to the C0 terminal status. |
| TD-11 | Hidden dependencies | NFR-01 | SDK/transport implicit retry configuration has not been inspected in the real model client. Offline tests prove only that the fake transport is called once per dispatch. |
| TD-12 | Guardrail debt | NFR-01 | The settlement exclusion is a static substring check on module source, not a behavioural assertion; it passes vacuously and would also trip on an unrelated comment. |
| TD-13 | Contract drift | NFR-01, NFR-02 | `dispatch` duck-types `prepared.status`/`prepared.messages` instead of validating the C5 `PreparedRequest` record, so a stub or a stale adapter can satisfy it. |
| TD-14 | Human/cognitive debt | NFR-01 | Resume is disabled by policy (a new run uses a new run_id). If the product later wants resumption, the spent counter must be restored without reset and the decision re-approved. |
| TD-15 | Verification debt | NFR-01, INV-02 | The Verify role is denied read on `docs/ai-use-log.yaml`, `docs/bug-diary.md`, `docs/debt-register.md`, `transcripts/` and `Report.md`, so check D of every Gate 4 review is only partial and record integrity rests on human review. Either allowlist those exact paths for `course-verify` or record a named human reviewer per feature. |
| TD-16 | Integration risk | NFR-01, INV-02 | Nothing prevents two `RequestBudget` objects from being constructed with the same `run_id`; each would then allow a full limit, so INV-02 holds per instance but not per run identity. C0 must guarantee a run id is bound to one budget (registry or construction site), and a test should assert it. |

## NFR-01 items (2026-11-16)

| ID | Status | Evidence / revision | Impact | Owner | Next review trigger | Mitigation | Closure proof |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TD-09 | Open | `pyproject.toml` `testpaths`; PR-NFR01-001 evidence | Acceptance cases can be skipped while CI looks green | CI maintainer (D7) | Next CI change | Add `test/offline` to the default collection and fail on skipped acceptance cases | A default `pytest -q` run reports the NFR-01 cases |
| TD-10 | Open (blocker for delivery) | `tradingagents/llm_clients/request_budget.py` has no non-test importer | NFR-01 is implemented but not enforced in any running flow | Integrator | Graph entry wiring PR | Instantiate the budget from the run context at graph entry, route both tiers, fallback and application retries through `dispatch`, map failures to C0 | Integrator receipt with integrated regression and a suppressed official rating on exhaustion |
| TD-11 | Open | Fake transport has no retry logic by construction | "No implicit retries" is unproven for the real client | Integrator | Model-client configuration review | Explicitly disable SDK retries for metered runs and assert the setting | Configuration assertion or client-level test in the integration receipt |
| TD-12 | Open | `test_t_nfr01_resume_no_settlement_coupling_in_module_source` | Exclusion is asserted statically, not behaviourally | NFR-01 owner | After integration | Add a behavioural check that no reconciliation path calls `dispatch` | Negative test or integrated trace showing no reconciliation dispatch |
| TD-13 | Open | `dispatch` uses `getattr`; test stub has only two fields | A drifted or stub adapter can pass | Integrator + NFR-01 owner | When C5 lands | Validate required fields or accept a typed protocol in C4 | Contract test using the real `PreparedRequest` |
| TD-14 | Accepted | Module has no reset/restore API; RP row states "never reset same-run counter" | A future resume request needs redesign | Product owner | Requirement change | Restore spent count without reset, with a new approval record | Approved delta specification and tests |
| TD-15 | Open | Gate 4 `ses_e1cab4f89ffed8ePmZwWo5Ljy0` reported denied reads on five record paths and did not bypass them | Every record-integrity verdict is partial, so a fabricated entry could pass review | Governance maintainer + NFR-01 owner | Next feature review | Add the five exact read paths to both permission files, or name a human reviewer in the memo | A Gate 4 session that reads the records, or a memo line naming the human reviewer |
| TD-16 | Open | Two budgets with one `run_id` each allow the full limit (see PR-NFR01-002) | A duplicate construction site would double the effective budget for one run | Integrator + NFR-01 owner | Graph entry wiring PR | Bind a run id to one budget in C0 and assert it | Integrated test that a second budget for the same run id is refused or shares state |
