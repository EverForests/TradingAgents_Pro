# Runtime policy catalog

| Requirement | Trigger | Deterministic action | Observable result |
| --- | --- | --- | --- |
| FR-01 / INV-01 | Invalid rating or unresolved required evidence | Reject; never publish or persist as official | BLOCKED with INVALID_RATING or INSUFFICIENT_EVIDENCE |
| FR-02 | Invalid/missing operand, provenance, unit or period | Exclude from verified metrics | UNVERIFIABLE with a reason |
| FR-03 | Missing/invalid optional sentiment source | Preserve coverage and reasons; continue market/financial analysis | NO_DATA / PARTIAL_DATA / AVAILABLE; zero coverage yields UNKNOWN and null |
| NFR-01 / INV-02 | No reservation available | Abort main analysis before send and deny publication | BUDGET_EXHAUSTED; no official rating |
| NFR-02 | Context above cap | Reduce optional blocks preserving required pairs; if still too large reject before reserve/send | CONTEXT_TOO_LARGE on failure; no budget debit for rejected request |

A provider failure after dispatch consumes the slot; no implicit retries are allowed in supported metered runs. Runtime diagnostic outputs must not masquerade as official recommendations.
