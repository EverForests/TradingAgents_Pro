# PR review memo

Add one dated entry per PR. Link pre-code plan/test approval and the actual results for the revision under review. Keep the memo free of credentials, student identifiers and raw session text.

| Required review area | What to record |
| --- | --- |
| Scope and spec | PR link, revision, reviewer, D1 IDs, requested versus actual behavior and fit criteria |
| Architecture | Owner module, ADR/invariants, integration boundaries and any changes to permissions, configuration or public API |
| Code and tests | Correctness, normal and negative cases, regression outcome, uncovered cases and residual risk |
| Security and efficiency | Untrusted model/data handling, traversal and secret exposure, authority bypasses, duplicate calls, output size or unjustified dependencies as relevant |
| Operations | Pre-code approval link and time; check commands and results; AI-use/session reference; runtime fallback, monitoring and rollback |
| Decision | Findings with owner or follow-up and one verdict: APPROVE, CHANGES REQUIRED, or REJECT |

## Entry template (copy for each actual PR)

- **PR / revision / date / reviewer:**
- **Requirements and invariants:**
- **Plan and tests approved before implementation:** reviewer, timestamp, and reviewed plan/test reference
- **Spec and architecture findings:**
- **Code and test findings:**
- **Security and efficiency findings:**
- **Operational metadata and evidence:** checks with pass/fail/not run; rollout/fallback; AI-use reference
- **Open findings and required action:**
- **Verdict:** APPROVE / CHANGES REQUIRED / REJECT

The team reported that a baseline and a test PR were completed. Add the verified link, observed check results and actual reviewer decision when available. That PR tests the merge mechanism; it does not establish implementation of every course gate. No PR verdict is recorded here without review evidence.

## Preparation revision under review

Scope: D1–D4/D9 documentation and schema; no application source, tests, runtime prompts, permission configurations or human-only rules are changed. Contracts C0–C5 and the readiness register are proposals for team review. Document authoring is not feature implementation approval. Record the eventual PR link, exact reviewed SHA and real human verdict after review; no APPROVE is supplied here.

For each future feature PR, add the base SHA, contract/fixture versions, shared-file owner and failing-before assertion. In Files changed, ensure the selected base excludes unrelated course scaffolding. If based on an unmerged document branch, target that branch initially; after its merge, retarget main and recheck the diff. Link raw evidence privately and only share redacted summaries publicly.
