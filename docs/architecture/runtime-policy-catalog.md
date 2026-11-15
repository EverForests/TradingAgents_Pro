# Runtime policy catalog

| Requirement | Trigger | Deterministic action / decision | Evidence to capture | Escalation or continuation |
| --- | --- | --- | --- | --- |
| FR-01 / INV-01 | Invalid rating or unresolved required evidence | Fail closed; never publish/persist rejected candidate | run ID, BLOCKED, INVALID_RATING/INSUFFICIENT_EVIDENCE, rejected-reference IDs without raw content | Stop publication; provide nonofficial diagnostic for human correction/rerun |
| FR-02 | Invalid/missing operand, provenance, unit or period | Exclude from verified metrics; UNVERIFIABLE | metric ID/reference, formula and sanitized validation reason | Continue other valid records; owner reviews unsupported source/period |
| FR-03 | Missing/invalid optional sentiment source | Preserve coverage/reasons; zero coverage -> UNKNOWN/null | source ID, requested window, valid-source count and missing reasons | Continue usable market/financial analysis; do not imply real-world silence |
| NFR-01 / INV-02 | No reservation available | Abort main analysis before send and deny publication | run ID, limit, charged/reserved count, BUDGET_EXHAUSTED | Human may start a new explicitly identified/configured run; never reset same-run counter |
| NFR-02 | Context above cap | Reduce optional groups preserving required pairs; irreducible -> CONTEXT_TOO_LARGE before reserve/send | scoped call site, bytes before/after, required retention/pair check, zero-send/debit assertion | Refuse affected run's official outcome; owner reviews required-block scope or cap before rerun |

A provider failure after dispatch consumes the slot; no implicit retries are allowed in supported metered runs. Runtime diagnostic outputs must not masquerade as official recommendations.

## Combined-path precedence (C0–C5)

1. Validate/reduce scoped context before reserving a model slot. CONTEXT_TOO_LARGE means no send or budget debit for that rejected request.
2. If context is ready but C4 has no slot, return BUDGET_EXHAUSTED. Both terminal paths suppress any earlier candidate as an official final recommendation.
3. Invalid financial records are excluded; optional sentiment failures preserve per-source reasons and UNKNOWN/null where appropriate. Continue usable analysis rather than treating absent sentiment as a neutral signal or unconditional publication failure.
4. On nonzero source coverage but failed assessment, keep PARTIAL_DATA/AVAILABLE and record assessment failure with UNKNOWN/null. Coverage is collection state, not model confidence.
5. Gate any resulting candidate at every official sink. A source placeholder is not substantive evidence. Publication passes only when C1 succeeds, regardless of a model's requested rating.

A user retry after a terminal failure is a new run with a new identity; do not resume the same metered identity with a fresh counter. Invalid configuration or unknown contract version blocks the affected task before live dispatch. These policies are proposed and require the relevant case evidence before being claimed as implemented.

The evidence fields above are planned receipt fields, not existing dashboards/counters. Implementers must show where each is produced; absent evidence remains a verification gap. This follows the new B3.1 catalog discipline of separating intended, implemented and unimplemented behavior.
