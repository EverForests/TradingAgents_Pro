# Requirement trace matrix

Planned paths and evidence; no pass results or test execution are asserted.

| Requirement | Enforcing component | Offline evidence planned | Runtime monitor |
| --- | --- | --- | --- |
| FR-01 | Publication gate and official sinks | Valid rating and evidence publish; bad rating/missing/unknown references fail across CLI/API/report/memory | Publication status, reason, accepted reference count |
| FR-02 | Verified metrics | Fixed-operand reproduction, signed difference, invalid provenance/unit/period/denominator, altered record and forged ID | Verified/unverifiable counts and reason codes |
| FR-03 | Sentiment coverage | 0–3 valid sources, genuine neutral, wrong ticker/window, continued analysis | Valid source count, reasons, missing score |
| NFR-01 | Request budget | Exact boundary, over-budget, concurrent reservations, isolated runs | Requests reserved/sent, limit, exhaustion |
| NFR-02 | Context limit | Short, reducible, irreducible, multibyte, pairing and required retention | Bytes before/after, reduction count, context rejection |
| INV-01 | Publication gate before every official sink | Zero declined candidates released or persisted | Blocked status and would-be publication violation |
| INV-02 | Atomic request reservation | Zero outbound requests beyond limit under parallel dispatch | Run request count versus cap |
