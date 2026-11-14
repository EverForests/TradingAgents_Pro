# Invariant register

| ID | Source | Enforcer | Verification | Operational fallback |
| --- | --- | --- | --- | --- |
| INV-01 | FR-01 | Publication gate before official sinks | Inject rejected candidates through CLI/API; check reporter and decision memory | Suppress official rating and memory append; emit BLOCKED reason. Quarantine any inconsistent result from downstream scoring. |
| INV-02 | NFR-01 | Per-run atomic dispatch reservation | Race two sends for last slot; verify actual transport requests never exceed cap | Reject further dispatches, mark the run BUDGET_EXHAUSTED and suppress the official rating. |

FR-02, FR-03 and NFR-02 remain independently testable acceptance contracts in D1. FR-02 verified fields exclude invalid records; FR-03 never coerces missing sentiment to neutral; NFR-02 prevents oversize sends in its declared scope.
