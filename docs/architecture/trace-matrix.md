# Requirement trace matrix

Proposed owner paths and evidence. Case IDs are defined in [verification constraints](../code-governance/verification-constraints.md) and D1; none imply executable tests or pass results. Shared contracts: [C0–C5](interface-contracts.md).

| Requirement | Enforcer / integration | Planned case IDs | Runtime monitor and failure |
| --- | --- | --- | --- |
| FR-01 | C1 `graph/publication_gate.py`, analyst/argument references and four official sinks | T-FR01-VALID/RATING/MISSING/REFERENCE/SINKS (expanded full IDs in D1) | publication_status, reason codes, accepted references; BLOCKED if rejected |
| FR-02 | C2 `agents/verified_metrics.py`, fundamentals/state/report | T-FR02-YOY/RATIO/DELTA/INVALID/IDENTITY | verified/unverifiable counts and reason codes; invalid records excluded |
| FR-03 | C3 `agents/sentiment_coverage.py`, sentiment/schema/state/report/downstream | T-FR03-COVERAGE/INVALID/NEUTRAL/PROPAGATION/SCORE | valid logical sources, per-source reasons, coverage and nullable assessment; optional data failure does not stop other valid analysis |
| NFR-01 | C4 `llm_clients/request_budget.py`, both-tier outbound path including fallback/retries | T-NFR01-BOUNDARY/RETRY/ISOLATION/FAILURE/RESUME | reservations, charged attempts, limit/exhaustion; refuse before over-limit send |
| NFR-02 | C5 `llm_clients/context_limit.py`, analyst closure and neutral debater then C4 | T-NFR02-SHORT/REDUCE/REJECT/UTF8/PAIRING/ORDER | final bytes, required-block retention, reduction count; CONTEXT_TOO_LARGE before reservation |
| INV-01 | C1 before CLI/API/report/memory, no free-text bypass | T-INV01-BYPASS, T-FR01-SINKS | rejected candidate release/persistence count must be zero; suppress/quarantine on breach |
| INV-02 | C4 atomic run-local budget and actual fake transport boundary | T-INV02-RACE, T-NFR01-BOUNDARY | actual outgoing requests above limit must be zero; refuse dispatch and publication |

Paths above are relative to `tradingagents/` except CLI adapters. Exact test filenames and shared adapter edits are frozen in each approved task plan. Requirement owners supply evidence for their feature; the integrator supplies a new receipt for combined components, not a copy of individual PR results.

## Implemented FR-03 evidence — 2026-11-17

The FR-03 row above now has an implemented mapping and recorded results in [the module handoff](../fr03.md#requirement-to-implementation-to-evidence-map) and [derived evidence](../fr03-evidence.json): COVERAGE / INVALID / NEUTRAL / PROPAGATION / SCORE all have concrete tests. Tested application b2816ec: 1533 regression passes, 100 subtests, 47 boundary controls and a separate configured 33-assertion paired replay. This is not evidence for other requirements, final publication/dispatch invariants or real-provider quality. The other proposed rows retain their owners' review states.
