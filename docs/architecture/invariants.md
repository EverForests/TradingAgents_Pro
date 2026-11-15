# Invariant register

Status: proposed; source statements are in [D1](../req/requirements.yaml). Operational failure actions implement the Nov-13 runtime-policy clarification: detecting a breach is not the response by itself.

| ID | Statement / source | Enforcer | Verification | Operational fallback |
| --- | --- | --- | --- | --- |
| INV-01 | A rejected candidate never appears as an official decision or enters decision memory; FR-01 | C1 publication gate before CLI, Python, official report and decision-memory sinks | T-INV01-BYPASS and T-FR01-SINKS: assert zero declined candidates released/persisted and show a bypass fails the negative test | Suppress official rating and memory append; emit BLOCKED reason; quarantine any inconsistent result from downstream scoring and block affected release |
| INV-02 | Actual requests in the metered main analysis never exceed the run limit, including concurrent dispatch; NFR-01 | C4 per-run atomic reservation and outbound boundary | T-INV02-RACE and T-NFR01-BOUNDARY: synchronized last-slot race and actual fake-send counts | Refuse further dispatch, mark BUDGET_EXHAUSTED, suppress official rating; do not reset spent counter to recover |

Fit threshold is zero violations. These are planned enforcement/tests, not passing results. FR-02, FR-03 and NFR-02 remain independently testable D1 acceptance contracts: verified fields exclude invalid records; missing sentiment never becomes neutral; oversized scoped messages never send. See [C0–C5](interface-contracts.md) and the [runtime policies](runtime-policy-catalog.md).
