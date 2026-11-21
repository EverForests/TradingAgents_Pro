# ADR-002 — Prospective repository enforcement without runtime changes

Current document review: **Approved**, recorded on 21 November 2026. [Offline review record](../../governance/offline-review-20261121.md) distinguishes current acceptance from historical implementation approvals and separate hosted review.

Date: 21 November 2026. Status: Approved in the confirmed offline team review; hosted peer review remains an independent operation.

## Context and decision

The coordinator requested repair of incomplete D7 enforcement while freezing application behavior. Existing CI success establishes only its executed jobs. Add one fail-closed `d7-required` aggregate and executable prior-test-approval, type/security/API/permission, schema, semantic and AI-use checks. Retain the entire existing regression selection. Execute policy from the trusted comparison base after the bounded first activation; do not use `pull_request_target` to execute untrusted code.

Application changes need genuine independent exact-test approval before their first implementation commit. A tests-only PR can retain this approval separately. No historical review or approval is reconstructed. For this repair the application-change approval condition is inapplicable because all application, prompt and existing-test bytes remain unchanged. Safety-path changes still need an ADR and hosted owner review.

Mypy analyzes original runnable source and governance scripts; duplicated `src/` is validated by byte/hash parity rather than imported twice. Third-party packages are opaque (`no_site_packages`), with missing third-party imports treated as dynamic. Existing source findings are recorded as exact fingerprints, including line and diagnostic identity. The new typed governance modules must have zero type errors. Bandit analyzes all in-scope Python source, including existing nosec annotations. Existing or individually reviewed tool-wrapper findings are disclosed in the initial security baseline. Baseline changes are protected governance changes, require this design to be revisited, and cannot silently expand the trusted-base budget.

The fixed semantic corpus contains complete source facts, expected outputs and explicit thresholds. Its evaluator rejects unsupported facts, contradictions and safety violations. Actual prompt/model changes additionally require output records tied to the full model/prompt configuration digest and frozen corpus; they cannot pass using the built-in fixture answers. Offline behavioral controls exercise all five application requirements. Deterministic controls and saved natural-model responses retain distinct evidence labels; no universal semantic-quality or investment-accuracy claim is made.

Protect `main` and `integration/course-project` with the trusted Actions aggregate, up-to-date branches, independent owner review and no administrator bypass, force pushes or deletion. Stored configuration is not proof of hosted enforcement; read-back and rejected-operation evidence are retained separately.

## Trade-offs and consequences

Preserving runtime bytes leaves explicit legacy typing/security debt. The gate prevents new findings; it does not claim a clean historical codebase. Prior-approval checks require review provenance and preserved Git ancestry, and refuse unsupported direct application pushes. The first installation cannot execute a policy absent from its base: permit only the explicitly identified governance-only activation, with all runtime hashes intact, then use base policy for subsequent changes. Human supervision and source truth remain outside what a CI log can prove.

## Verification and rollback

New tests live only under `test/governance/`. The pre-implementation workflow contract recorded five meaningful failures and one existing positive control. Positive and deliberately invalid inputs, source-analyzer mutations, fixed behavioral selections and the full prior suite provide separate receipts. Reverting this governance change does not alter business behavior; restoring hosted protection is an explicit administrator operation and is never done merely to obtain a green check.

## Execution follow-up — 21 November 2026

Decision: retain only sanitized receipts and explicitly include the hidden receipt directory in Actions artifact upload. The first hosted run44883183291 passed the check executions but failed upload, and the aggregate refused success. Corrected PR run44883596229 passed. The push event independently required the changed safety ADR; this dated decision accompanies the workflow maintenance rather than weakening that requirement.

The single authorized full local invocation returned1799 passes and33 baseline-Git-provenance setup errors. Only the affected FR03 module was recovered against a genuine9fa1196 Git worktree, with33passes; no second manual full run occurred. New governance64cases and the14behavioral selections remain separate counts. Retain115type and34security/tool findings as explicit exact budgets. Model receipt consistency does not authenticate its origin, and substantive human design/source-support review remains necessary. [Full measured account](../../governance/d7-verification.md).

## Coordinator scope decision — 21 November 2026

Status: main protection saved and read back; integration protection declined. The coordinator explicitly directed leaving integration's settings unchanged. Decision: retain main as the protected release boundary and keep integration as an unprotected development branch. Passing or failing integration CI is informative, not an enforced merge condition there. This overrides the initial two-branch protection target and is disclosed rather than claiming full protection on all working branches.

## Exact blueprint allowlist correction — 21 November 2026

Decision: add only the root `architecture-blueprint.md` document to the first-activation file allowlist. The coordinator approved this CI repair and delivery synchronization after the documentation-only revision `d7051fb` exposed the omission. The blueprint is already an approved course architecture artifact; its current review-status update changes no application behavior. No root wildcard, new runtime path, agent permission, policy-snapshot exception or hosted protection change is introduced. The immutable reviewed policy snapshot, ancestry checks, tamper rejection and fail-closed aggregate remain intact.

The PR workflow rejected the blueprint during bounded bootstrap. On push, the ordinary checks and policy/static stages passed, but the two pinned-bootstrap governance cases reached the same premature scope rejection. The aggregate consequently failed for both events. This follow-up changes no tests, application source or prompts and runs no additional local tests. Exact-revision hosted results are retained in GitHub Actions; earlier measured receipts retain their original revision identities.
