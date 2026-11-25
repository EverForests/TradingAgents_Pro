# D7 enforcement verification — 21 November 2026

## Revisions and authority

The application remains `df8a9d6419dfa0aab2f4d8986d0a44060354cdb9`. Governance activation is bounded at `7da6ecc9ff665d096b3def5be9ee9601628ae05e`; the initial policy snapshot is `5da11c8121397aa516245ff171857e38c6dd7248`, selected by the workflow at `746b6bc578d0593075493221c08acbf174ec0f50`. This coordinator-authorized repair changes governance, development checks and documentation. The 331 frozen application, runtime-prompt, source-copy and existing-test files are byte-identical. Runtime dependencies and agent edit permissions are unchanged. Exact read-only grants permit OpenCode to inspect the approved governance artifacts.

The new policy applies prospectively. It does not reconstruct missing historical test approvals. Its first installation is explicitly restricted to the reviewed governance/document scope and immutable policy snapshot. Subsequent evaluations execute policy from the comparison base. Public PR #11 retains the integrated change history; a later merge still requires the actual reviewer and repository conditions.

## Measured local checks

| Check | Actual observation | Interpretation |
| --- | --- | --- |
| Before implementation | Workflow contracts: 5 intended failures, 1 positive pass at `cf90cac` | Absent required controls were exposed before governance implementation; no import error counted as a defect. |
| Governance suite | 64 passed | Positive and deliberate-negative approval, API/permissions/schema, analyzer, semantic and aggregate controls, including pinned-bootstrap tampering. |
| Source analysis | 115 type findings; 34 security/tool findings; zero new fingerprints; zero typing errors in new D7 modules | Exact reviewed debt budget, not a clean-source claim. Diagnostic location and source/code digest are pinned; removed findings are allowed, new ones fail. |
| Fixed semantic rubric | 9 complete annotated synthetic cases pass | Required-field agreement 100%; no declared safety escape or unsupported fact. These are deterministic rubric controls. |
| Five-feature behavioral selection | 14 passed; JUnit count and no skipped/error/failure cases enforced | Real existing test entry points execute; an empty successful selection cannot pass. These overlap other suites and are not added to their totals. |
| Whole-repository Ruff and patch hygiene | Passed | Separate from source typing and security results. |
| One authorized full local offline invocation | 1,799 passed, 33 setup errors, 1 skipped, 1 deselected; 100 passing subtests | All 33 errors came from the FR-03 comparison fixture pointing to an exported source directory without genuine Git HEAD metadata. No behavioral assertion failed. |
| Recovery, only affected module | 33 passed with a real `9fa1196` detached upstream worktree | Corrected provenance for the affected fixture. No second manual full-suite run was performed. |

The historical application receipt of 1,832 passes is retained separately. The split local rerun and recovery are not described as a newly executed all-green full run. Optional Bedrock and explicitly excluded real-provider cases retain their original exclusion explanations. No new live product-model or market acceptance run was made during this repair.

## Actual hosted execution and refused aggregate

[PR workflow run 44883183291](https://github.com/EverForests/TradingAgents_Pro/actions/runs/44883183291), at `746b6bc`, passed all four Python regression jobs, schema/reference checks, clean install, lint, policy, source analysis, 64 governance cases and the fixed semantic/behavior replay. Its receipt-upload step failed because the artifact uploader excluded the hidden `.d7-receipts/` directory. The required aggregate consequently failed. This is an observed fail-closed integration result, not a fabricated mutation. The workflow was corrected to retain explicitly sanitized hidden receipts. The corrected hosted result and protection read-back are recorded below when observed.

## Enforcement scope and limits

- Prior approval requires a real independent repository collaborator's GitHub APPROVED review of an exact tests-only ancestor revision, after that revision and before the first implementation. The plan and test scope are retained, and later edits to approved tests are refused. Business implementation cannot use governance-only tests as its approval evidence.
- Type/security budgets disclose inherited problems and narrowly reviewed fixed-argument tool wrappers. Mypy treats unavailable third-party packages as opaque; the gate does not establish deep type correctness inside those packages. Security findings are scanner observations, not independently proven exploitable vulnerabilities.
- API/record signatures, runtime dependencies, source copies, safety ADRs, CODEOWNERS and permission-copy/edit boundaries are checked. Human review must assess the ADR's relevance; text presence alone cannot prove sound design.
- Model/prompt or coding-agent instruction/model changes require actual retained model response content, recomputed content hash, exact configuration/corpus identity and frozen-rubric agreement. Metadata consistency is not cryptographic proof of provider authorship. Human provenance/source-support review remains necessary. Unchanged model code receives deterministic controls rather than a new natural-model quality claim.
- Schema, regression and AI-use evidence remain distinct required jobs. A new AI-use entry is required for the covered change scope; the log does not itself prove authorship or human approval.
- Hosted branch protection is a separate operation. Workflow definitions and local passes alone cannot establish protected merging. Historical approval gaps, investment accuracy and incomplete live message-byte instrumentation are not closed by this repair.

## Reproduction

From a full Git clone with development dependencies installed:

```sh
python -m pytest -q test/governance
python .github/scripts/d7_policy.py --base <exact-comparison-base>
python .github/scripts/d7_static.py
python .github/scripts/d7_semantic.py --base <exact-comparison-base>
```

Use trusted-base scripts as CI does for actual PR enforcement. Bare source exports cannot establish commit ancestry. The upstream comparison requires a genuine `9fa1196` checkout; supplying only identical source bytes is insufficient for a test that verifies `git rev-parse HEAD`. The private package includes bounded provenance metadata and reproduction instructions; complete historical governance review should use the public full clone.

Sanitized machine receipts are in [evidence](evidence/). Raw OpenCode plan/review output and local terminal logs remain outside the public repository. See [ADR-002](../architecture/adr/002-d7-enforcement.md) and [maintenance plan](d7-repair-plan.md).

## Follow-up hosted receipts and read-only review

Corrected [PR run44883596229](https://github.com/EverForests/TradingAgents_Pro/actions/runs/44883596229), at `ade2b08052e531e2b5934988541cd8671fb9b46f`, passed all nine jobs including `d7-required`; sanitized receipt upload succeeded. The same revision's push-event policy independently rejected the absence of a changed accompanying ADR. ADR-002 now records the receipt-maintenance decision; this is corrected by supplying the required artifact, not disabling that rule.

OpenCode's final read-only disposition found no new code-level blocker after reading the actual corrected scripts and tests. It explicitly attributed terminal/hosted results to the maintainer and retained third-party typing, historical approval and model-origin limitations. Its remaining external condition was integration-branch protection after the last maintenance push. Raw output remains private; this paragraph is an attributable review summary, not an independent human approval.

The `main` rule was saved and read back in the normal authenticated GitHub UI: require PR, one code-owner approval, dismiss stale approvals, approve the latest push, require up-to-date branches, bind `d7-required` and the existing timezone regression to GitHub Actions, resolve conversations, enforce administrators, and forbid force pushes/deletion. [Read-back record](evidence/main-protection-readback.json). The interface also recognized `asling3` as an actual code owner on the controlled PR; no new account access was granted.

[Controlled PR12](https://github.com/EverForests/TradingAgents_Pro/pull/12) changes only a disposable governance document and intentionally omits a new AI-use record. It provides a real negative-policy/aggregate observation. It must never merge. Integration protection and the resulting disabled merge are recorded in a separate current read-back receipt after the last ordinary maintenance push.

## Coordinator disposition and latest delivery checks

The coordinator explicitly chose **not** to save integration-branch protection. A transient integration rule was removed at the coordinator's explicit direction. The final GitHub rule list was read back and contains only main. Integration remains a development branch without a required-check/independent-review merge rule. Its CI failures are visible but do not themselves prevent merging there. The protected release boundary is `main`, whose saved settings remain unchanged. This supersedes the initial maintenance plan's intention to protect both branches and OpenCode's earlier external condition; enforcement is claimed only for the actual protected boundary.

At delivery revision `e480c2a4636915c50bf1e30b9afa8c71ed224e5a`, both [PR run44884725839](https://github.com/EverForests/TradingAgents_Pro/actions/runs/44884725839) and [push run44884720516](https://github.com/EverForests/TradingAgents_Pro/actions/runs/44884720516) passed. The accompanying ADR decision resolved the earlier push refusal without weakening policy. PR12 retains two explicit experiments: its first revision omitted AI-use evidence against integration; its later deliberately duplicated AI-use ID is intended for the protected main boundary. The PR's actual check/merge status records which operation is refused. Neither experimental revision is to be merged.

## Observed protected-release negative control

PR12 was retargeted to `main` and refreshed at `fcce84e9860de16cbc0c60095d70c15c9797b2e8` so the target comparison was actually executed. [Run44885810283](https://github.com/EverForests/TradingAgents_Pro/actions/runs/44885810283) passed seven jobs, failed the deliberately duplicated AI-use ID in the artifact/schema job, and failed the aggregate. GitHub marked `d7-required` Required, displayed **Merging is blocked** and disabled **Merge pull request**; the independent latest-push approval was also absent. This is an actual protected-main refusal, rather than inferring enforcement from a YAML file. The [read-back receipt](evidence/release-negative-control.json) separates it from the earlier missing-log control against integration. The experimental PR is closed without merging; the integrated release branch contains neither invalid record.

## Blueprint document-scope correction — 21 November 2026

Documentation revision `d7051fb` produced 14 successful and four failing checks across its push and PR workflows. The ordinary regression matrix, installation, lint and course-artifact jobs passed. [PR run44890380337](https://github.com/EverForests/TradingAgents_Pro/actions/runs/44890380337) rejected the root blueprint during bootstrap with `Bootstrap is restricted to the approved governance and document scope`. [Push run44890376310](https://github.com/EverForests/TradingAgents_Pro/actions/runs/44890376310) passed policy/static analysis but its governance selection returned 62 passed and two failed: both pinned-bootstrap cases encountered that same premature scope rejection. Both required aggregates then failed closed.

The approved correction adds only `architecture-blueprint.md` to the existing exact root-document allowlist. Existing tamper assertions, pinned governance bytes, ancestry checks, source contracts and release protections are preserved. No application, prompt or test file changes, and no further local test run, accompany this maintenance. The fix revision's actual push and PR execution is available in [the CI workflow history](https://github.com/EverForests/TradingAgents_Pro/actions/workflows/ci.yml); historical green and negative-control receipts above continue to describe their original revisions.
