# Memory and state design

Current document review: **Approved**, recorded on 21 November 2026. [Offline review record](../governance/offline-review-20261121.md) distinguishes current acceptance from historical implementation approvals and separate hosted review.

| Requirement | Session state and lifecycle |
| --- | --- |
| FR-01 | Evidence/argument IDs and candidate status are scoped to one run; only allowed decisions reach existing decision memory. Do not resolve references from a prior run. |
| FR-02 | Verified records are immutable within a run; report may retain source references and immutable calculation records. No user-wide metric cache in first release. |
| FR-03 | Coverage and reasons are run-local; avoid persisting raw social responses. |
| NFR-01 | Counter is run-local; a resumed metered run must not reset spent slots. Disable upstream checkpoint resume for metered course runs until counters can be restored atomically; restart is a distinct run. |
| NFR-02 | Reduction is per request; optional context may be dropped from the sent payload only, not silently erased from approved evidence records. |

Reuse the upstream user-owned decision log for approved decisions only and retain its configured rotation/deletion behavior. Keep course fixtures isolated from users' local caches and memory. Reports may contain nonsecret source metadata; users control local retention. No credentials, raw model sessions or student identifiers belong in public logs. Repeatability claims require a new run or an explicitly versioned snapshot, not a retained LLM answer.

## Shared state contract

Use C0 identity and C1–C3 authoritative records from [interface-contracts.md](interface-contracts.md). Add coverage/assessment state beside existing sentiment text; downstream readers use authoritative fields rather than reparsing a Neutral placeholder. Keep data coverage, assessment failure, execution completion and publication approval separate. New runs never inherit prior scores, references or counters.

Raw prompts, account details, personal API keys and complete vendor/social responses stay out of public logs and repository fixtures. Keep original private run receipts separately from shareable, synthetic test fixtures; record only approved references/hashes in public artifacts. Determine the team's actual retention duration before collecting new live payloads; no indefinite retention is implied.
