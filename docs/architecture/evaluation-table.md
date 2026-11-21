# Candidate evaluation

Current document review: **Approved**, recorded on 21 November 2026. [Offline review record](../governance/offline-review-20261121.md) distinguishes current acceptance from historical implementation approvals and separate hosted review.

Design assessment only; no benchmark results are claimed.

| Candidate | FR-01 | FR-02 | FR-03 | NFR-01 | NFR-02 | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| Prompts and existing settings only | Can ask for citations; cannot enforce publication | Model arithmetic remains unchecked | Can describe missingness inconsistently | Per-loop limits do not bound total requests | Provider output limits do not bound serialized input | Reject |
| Local deterministic components at existing seams | Shared release result | Verified metric registry | Typed coverage | Per-run reservation | Deterministic scoped preparation | Selected: least change to baseline while supporting all fit criteria |
| Rewrite orchestration | Possible but migrates all sinks | Possible | Possible | Possible | Possible | Defer: broader regression and integration cost without present need |

Re-evaluate against the ADR triggers and the five fixture groups in the trace matrix. Use fixed inputs before comparing timings or token use; early failures are not performance improvements.
