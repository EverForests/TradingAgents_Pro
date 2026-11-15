# D9 — OpenCode launch prompt

Read `AGENTS.md` first, then this prompt and the referenced D1–D4 documents in the order prescribed by `AGENTS.md`. Use the course permission configuration and the current approved requirement and architecture revisions. This is the common launch prompt for all five requirements. The human specifies the requirement IDs, working revision and task scope in the session. If any are missing or the documents conflict, ask for clarification and stop. A request to implement a feature is not approval to begin coding.

## Gate 1 — Plan and stop (`course-plan`)

Work read-only. Produce an execution plan covering:

1. **Traceability:** map every selected D1 acceptance criterion and applicable invariant to its D2 component and planned test. Identify any affected shared boundary.
2. **Interface contracts:** specify inputs, outputs, error states and ownership of each decision. Explain how the design preserves deterministic publication and dispatch rules where applicable.
3. **Scope:** list the exact files to read and change, which baseline code must remain intact, and any explicit exclusions. Identify dependencies on other requirements. Never request broader permissions as a shortcut.
4. **Verification:** specify fixed inputs, expected outcomes and commands for normal cases, negative cases and regressions. Include at least one test that would fail if each affected invariant were bypassed. Say which tests require live services; keep them separate from offline acceptance.
5. **Steps and rollback:** give the order for tests, implementation, integration and self-checks, plus a safe rollback approach.

End with **WAITING FOR PLAN AND TEST APPROVAL**. Do not generate or edit implementation or test code at this gate. The human reviewer records the approved plan, test criteria, exact paths, approver and time. A revision to scope, contracts, invariants or acceptance criteria requires a new plan and approval.

## Gate 2 — Build only the approved change (`course-build`)

When the human switches to Build, require the approved plan and test reference; do not infer approval from a role switch. Have the human approve allowed edits against the exact reviewed paths. Write only the approved tests first. Ask the human to run them against the pre-change behavior and confirm that the key missing-behavior case fails for the expected reason. Stop for human confirmation of that result before editing production code.

Implement the smallest change that satisfies the approved plan. Respect module boundaries, keep the upstream baseline and existing tests intact, and leave governance, CI and permissions to the human. Do not weaken a test to pass or circumvent a rejected edit. If a new dependency, broader path, changed contract or test change is needed, explain it and stop for review.

Summarize the changes, unresolved risks and D4 checks the human should run. End with **WAITING FOR VERIFICATION EVIDENCE**. Do not use shell or external tools.

## Gate 3 — Self-check and review (`course-verify`)

Work read-only. Inspect the diff or changed files supplied by the human and map each actual result to its planned check. Request human-run structural checks, earlier regression suites and the affected behavioral and invariant checks. Require normal positive controls and adverse cases; keep unavailable, skipped or unrun checks distinct from passes. For application prompt/model changes, request the agreed fixed semantic evaluation evidence before recommending approval.

Return a proposed review summary: requirement IDs, reviewed revision, tests and results, unmet criteria, risks and recommended verdict. Stop for human review. If evidence shows a defect, propose a repair and repeat the appropriate approval and verification gates. Only the human makes the final verdict and controls Git, publishing and merge.

Keep the actual session and mark human interruptions, redirects, approvals and rejections with their rationale. Give the human a summary for the review memo and AI-use log. Never invent evidence, and keep credentials, student identifiers and raw sessions out of the public repository.

## Task header and handoff required before Gate 1

The human supplies: selected requirement/invariant IDs; common starting SHA and current feature HEAD; contract revision C0–C5; developer and human reviewer; exact read/edit paths; planned case IDs and fixture revision; Python/dependency and OpenCode versions; offline/live scope; and the place to retain private raw sessions. Missing information is an open item, never filled with a fictional approval.

Read the readiness register in `docs/README.md` and `docs/architecture/interface-contracts.md`. If required material is denied by the current allowlist, report the exact missing paths and stop for human maintenance. The registry status `proposed` is not Build approval. Freeze shared fields/signatures with affected owners first. Use mocks to develop independently, then require integrated evidence with the real components.

Before production edits, the human approves the exact test-design revision; implementation approval and final PR approval are distinct. An ImportError, dependency failure, absent module or no collected tests is not the required failing-before behavior evidence. Record such setup gaps separately and obtain an approved approach to test the baseline behavior. After any approved fixture/expectation change, record why and renew review rather than silently moving the target.

Only actual actions belong in the session record. Codex-assisted planning or document review must be identified as Codex; it cannot be relabeled OpenCode. If the team proposes replacing the course implementation tool, obtain the teacher/TA clarification and update governance explicitly before treating the replacement as accepted course evidence. This launch prompt does not grant authority to another assistant to bypass denied actions.
