# Memory and state design

| Requirement | Session state and lifecycle |
| --- | --- |
| FR-01 | Evidence/argument IDs and candidate status are scoped to one run; only allowed decisions reach existing decision memory. Do not resolve references from a prior run. |
| FR-02 | Verified records are immutable within a run; report may retain source references and immutable calculation records. No user-wide metric cache in first release. |
| FR-03 | Coverage and reasons are run-local; avoid persisting raw social responses. |
| NFR-01 | Counter is run-local; a resumed metered run must not reset spent slots. Disable upstream checkpoint resume for metered course runs until counters can be restored atomically; restart is a distinct run. |
| NFR-02 | Reduction is per request; optional context may be dropped from the sent payload only, not silently erased from approved evidence records. |

Reuse the upstream user-owned decision log for approved decisions only and retain its configured rotation/deletion behavior. Keep course fixtures isolated from users' local caches and memory. Reports may contain nonsecret source metadata; users control local retention. No credentials, raw model sessions or student identifiers belong in public logs. Repeatability claims require a new run or an explicitly versioned snapshot, not a retained LLM answer.
