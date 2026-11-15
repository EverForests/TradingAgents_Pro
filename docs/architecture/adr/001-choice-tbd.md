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

## Contract revision and token-budget design

[Contracts C0–C5](../interface-contracts.md) refine this proposed decision. Source validity is determined from collection metadata, not model prose. A measured Neutral/5.0 is legal; no usable source forces UNKNOWN/null. Partial coverage and assessment failure are separate. Publication and dispatch remain deterministic authorities across structured and fallback paths.

Teacher Project P5 additionally requires an input token cap and compaction threshold. Proposed architecture setting for review: `T_input_cap = 16384` tokens, trigger compaction above `floor(0.8 * T_input_cap) = 13107`, with an independently configured output allowance and provider-envelope reserve. This is a **design proposal**, not a verified limit or new completed requirement. Before adopting it, verify the actual school model context capacity, tokenizer/counting method, schema overhead and provider conversion; record these in the approved run configuration. Do not estimate a hard token bound as bytes/4. If reliable counting is unavailable, mark token enforcement unverified and block claims of token-budget compliance.

Assemble identity/task, standing constraints, evidence/state, active tool exchanges, optional history and current request; prioritize/deduplicate optional groups, budget, compact, reinject standing constraints, and recount before send. Preserve critical content and tool pairs; if mandatory context cannot fit, refuse the scoped request. NFR-02 independently retains its 65536-message-byte fit criterion and two-call-site scope. A byte-gate implementation alone must not be reported as this token policy. Review whether a token guard is needed for the selected course release after the live probe; do not silently expand all five features.

Reopen this ADR if approved fields, date semantics, token settings, scope or fallback actions change. Record the human decision, supporting test evidence and affected documents; no approval is supplied by this draft.


## Interface v1.0 selection

Use JSON-compatible shared records and the callable boundaries in C0–C5; private internal types remain replaceable through adapters. Extend the existing AgentState with separate owner keys instead of a common nested dictionary that parallel nodes could overwrite. Preserve legacy report strings as views, not alternative authority. At 0/3 sources, FR-03 skips the sentiment model and emits deterministic UNKNOWN/null. This is a proposed decision for team confirmation, not implementation or test approval.

The product run-profile request limit starts at a configurable 40; limit 3 remains only a boundary-test fixture. Reproduction attempt caps of 16/20 belong to separate diagnostic tooling and user approvals. Checkpoint continuation in that tooling does not implement application budget resume. Profile thinking-disabled and 4096 output tokens are initial settings to verify, not teacher-prescribed thresholds. Changes justified by completed runs update configuration evidence; changes to shared authority/fields update this ADR and affected tests.
