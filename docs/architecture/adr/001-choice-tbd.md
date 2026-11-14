# ADR-001 — Extend the graph with deterministic checks at existing boundaries

Status: proposed; no approval or implementation implied.

**Drivers.** Preserve the baseline and demo schedule, prevent invalid outputs, make failures observable, and give each requirement an offline acceptance test. The baseline has structured decisions, reporting and reusable clients, but a free-text fallthrough and multiple publication paths require explicit integration.

**Decision process.** Identify actual dispatch and publication paths, compare the options in the evaluation table, agree contracts, then review counterexamples before implementation. Adopt local typed checks and shared entry boundaries rather than prompt-only constraints or a new orchestrator.

| ID | Design decision |
| --- | --- |
| FR-01 | Resolve evidence in the current run and use one deterministic gate result at every official sink. |
| FR-02 | Compute once from validated operands and resolve verified values by ID; never trust numeric values copied into model prose. |
| FR-03 | Carry coverage and nullable score separately from execution state. |
| NFR-01 | Count dispatch at a common transport boundary; atomically reserve a slot per run. |
| NFR-02 | Size final serialized messages, reduce only optional blocks and fail before reserving a slot. |

**Runtime model context.** In priority order: role and task; standing constraints; typed evidence and run state (IDs, metrics and coverage); current tool exchanges; optional older discussion; current request. Tag mandatory blocks explicitly. Deduplicate only optional history, preserve paired tool calls/results, prioritize newer optional messages, serialize deterministically as UTF-8 and drop optional blocks oldest first until within the configured cap. Trigger compaction above 64 KiB at the proposed gate settings. This is a byte cap, not a token guarantee; do not infer one token budget for all providers. Reassemble and assert all standing constraints and required blocks are present after reduction; reject before transport if they cannot fit.

**Consequences.** Minimal upstream changes and explicit rejection states; shared dispatch and publication integration must be reviewed together. Reopen if any provider hides retries, any official sink bypasses the gate, required evidence routinely cannot fit, or a proposed feature requires genuinely different orchestration.
