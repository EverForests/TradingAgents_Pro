# CS5351 agent entry point

Build target: extend the existing single-stock TradingAgents application for FR-01–FR-03 and NFR-01–NFR-02. The unchanged reference is `upstream-baseline` at `9fa1196fffbcfd9de5146d2dd2869df84ab99838`. Preserve `tradingagents/`, `cli/` and the existing test suite; add course tests under `test/offline/` and `test/live/`.

Documentation: [index](docs/README.md), [C0–C5 contracts](docs/architecture/interface-contracts.md) and [review records](docs/review-memo.md). Use the approved specification revision. Report missing allowlist paths to the human maintainer before the affected operation.

Read in order: [D1 registry](docs/req/requirements.yaml), [blueprint](architecture-blueprint.md), [ADR](docs/architecture/adr/001-choice-tbd.md), [invariants](docs/architecture/invariants.md), [trace matrix](docs/architecture/trace-matrix.md), [state](docs/architecture/memory-design.md), [permissions](docs/architecture/permission-model.md), [runtime policies](docs/architecture/runtime-policy-catalog.md), [candidate evaluation](docs/architecture/evaluation-table.md), then [structural constraints](docs/code-governance/structural-constraints.md), [tool rules](docs/code-governance/mcp-tool-manifest.md) and [covenant](.agent/rules.md).

After reading this entry point, follow [Prompt.md](Prompt.md) as the shared launch prompt. Plan first: name requirements and invariants, list exact files and contracts, specify independent normal/negative tests and rollback. Stop for recorded human approval of plan and tests before generating any implementation. Use the approved path list on each tool request. Configured writable paths are an outer limit; task approval may narrow them further. Governance, baseline history, existing tests and external data are frozen to the agent.

Verify imports and module boundaries, baseline regressions, each fit criterion and safety counterexamples. Offline runs use fixed fixtures and fake transport; live checks are separate and human-run. Record commands/results and actual interventions; mark unrun checks honestly. Submit a proposed change for human review; never merge, publish or widen permissions yourself.

Coordination: one owner per requirement and an explicitly agreed integrator for shared files. Follow the course OpenCode implementation workflow. Keep preparation/review distinct from implementation evidence and record the actual tools, scopes and sessions in the AI-use log. No auxiliary workflow may bypass course-role restrictions.
