# CS5351 deliverable map

This branch provides D1–D4 requirements, architecture and governance, and the shared D9 launch prompt. D4 defines verification and evidence recording; planned cases and reported observations are not test results. D5–D8 course artifacts remain scaffolded unless separately implemented. Wiring the schema and verification checks into required CI gates is part of D7. Load the OpenCode policy explicitly as documented in the permission model and verify its effective permissions before use.

| Deliverable | Planned location |
| --- | --- |
| D1 — Requirements | `docs/req/product.yaml`, `docs/req/requirements.yaml`, `docs/req/req-schema.json` |
| D2 — Architecture | `architecture-blueprint.md`, `docs/architecture/` (including ADRs, invariants, trace matrix, memory, permissions, evaluation and runtime policies) |
| D3 — Coding governance | `AGENTS.md`, `docs/code-governance/`, `.opencode/`, `.agent/` |
| D4 — Verification governance | `docs/code-governance/verification-constraints.md`, `docs/review-memo.md`, `docs/debt-register.md`, `docs/bug-diary.md` |
| D5 — Session evidence | `transcripts/` in the course submission; keep raw sessions out of the public repository |
| D6 — Process report | `Report.md` in the course submission; keep student identifiers out of the public repository |
| D7 — Repository and gates | `README.md`, `.github/workflows/ci.yml`, and branch protection settings |
| D8 — Source and tests | Existing implementation: `tradingagents/` and `cli/`; existing tests: `tests/`. Course submission paths: `src/` and `test/`, with new course tests split into `test/offline/` and `test/live/`. |
| D9 — Static launch prompt | `Prompt.md` at the repository root; versioned runtime prompts belong in `prompts/`. |

Maintain the project AI-use log at `docs/ai-use-log.yaml` without credentials or personal information. Verify the source and test layout when assembling the submission ZIP. The scaffold does not move upstream modules, change test discovery, or add blocking checks.
