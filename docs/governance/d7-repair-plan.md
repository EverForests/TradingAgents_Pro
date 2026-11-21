# D7 enforcement maintenance plan

Date: 21 November 2026. Starting revision: `7da6ecc9ff665d096b3def5be9ee9601628ae05e`.

## Authorization and review provenance

The coordinator requested repair of D7 without business-code changes, coordination with OpenCode, synchronization of public/private materials, and revision of presentation materials against the teacher's announcement. The coordinator's continuing authorization permits the maintenance operator to choose routine implementation and verification details. This is a contemporaneous task authorization, not a reconstructed historical peer approval or a submitted GitHub Review.

OpenCode `course-plan`, using the configured school DeepSeek model, read the existing governance and CI artifacts and produced a read-only plan in session `ses_e031006c3ffeX6NzfdNuWB7B6d`. Native output is retained privately. The operator adopts a single workflow, exact finding baselines, trusted-base policy execution, explicit applicability and real hosted review requirements. The operator rejects the draft's implication that a pull-request workflow automatically comes from the base, its requirement that reviewers belong to different organizations, and any blanket advisory semantic bypass. Reviewers must be independent of the PR author and have repository authority; fixtures remain blocking even when a model-change receipt is inapplicable.

## Allowed changes

Governance implementation: `.github/scripts/d7_*.py`, `.github/governance/**`, `.github/workflows/ci.yml`, `.github/CODEOWNERS`, `test/governance/**`, `mypy.ini`, development-only dependencies in `pyproject.toml`. Maintenance documents may change under `docs/`, `README.md`, `Report.md`, and task-specific read-only permissions in the two OpenCode configuration copies. Presentation and private package changes stay outside the source repository. A governance ADR records these choices.

Frozen paths: `tradingagents/`, `cli/`, `src/`, `main.py`, `prompts/`, `tests/`, `test/offline/`, `test/live/`. Before/after file hashes must agree. Runtime dependencies must remain unchanged. No live market/model product acceptance run is requested.

## Executable acceptance and order

1. Add workflow-contract tests first. Against the starting workflow, require genuine failures for the absent required aggregate, typing/security execution, prior-approval enforcement and semantic enforcement. Import/dependency failures do not count.
2. Implement approval/history, static/type/security/API/permission/schema, semantic and AI-use checks. Type and Bandit analysis inspect real source; exact reviewed finding baselines disclose existing debt. Newly introduced findings fail.
3. Add positive and deliberate-negative governance cases. Test no/late/self test approval, unknown references, changed runtime dependencies, mismatched permissions, expanded API without ADR, unsupported semantic claims, missing model-linked evidence, and failed/missing/skipped aggregate jobs. Mutations use disposable synthetic files, not application edits.
4. Run fixed behavioral selections for all five requirements, the frozen semantic corpus, governance tests, lint, type/security/dependency checks and the complete prior offline suites. Retain separate historical application counts and new governance counts.
5. Configure hosted protection for `main` and `integration/course-project`: required trusted `d7-required`, up-to-date branches, at least one independent code-owner review, stale-approval dismissal, no force pushes/deletions or administrator bypass. Read back actual settings and use a controlled failing check when access permits. A local declaration alone is not hosted enforcement.
6. OpenCode `course-verify` inspects the actual patch and measured receipts. Correct defects and update public/private audit, report and ten-minute-video material only to the demonstrated state. Publish no student numbers, private raw sessions or credentials.

## Prior approval and activation

New application implementation requires an independently approved exact test revision that is an ancestor of its first implementation commit, with a genuine GitHub review submitted before that implementation. The checker obtains review metadata from GitHub rather than trusting a PR author's JSON declaration. A separate tests-only PR may supply durable approval. Historical application code remains attributed to historical evidence and is not retroactively approved. This maintenance changes governance rather than application behavior; the new gate's application approval condition is explicitly inapplicable to this bounded repair, while safety/ADR and hosted final-review requirements still apply.

## Rollback

Revert only the governance maintenance commits and restore recorded branch settings through the administrator. Do not erase historical records or force-push shared history. Preserve private evidence and the frozen runtime hashes. An unavailable remote review or setting is recorded as an enforcement limitation, not silently accepted.
