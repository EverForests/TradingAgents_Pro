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

## Preparation follow-ups

- TD-06: original financial operands and full five-run configurations/raw traces are still absent. One supplied AAPL narrative and a summary do not replace them. Close only with reproducible fixtures and receipts.
- TD-07: actual OpenCode guard probes and all course CI gates remain unverified; adding prose does not close this debt. Resolve exact-path omissions before affected Build tasks.
- TD-08: five independent Codex chats may drift on interfaces or claim approvals from summaries. Use one contract revision and real human review links; keep actual tool identity and shared-file ownership explicit.
- Context architecture: proposed token budget in ADR-001 still needs tokenizer/model-capacity validation; a 64 KiB message check alone cannot close it.
