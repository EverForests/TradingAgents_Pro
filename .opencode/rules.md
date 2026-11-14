# OpenCode rules — human-maintained

- Plan and Verify are read-only. No Build edits before the human approves scope, tests and contracts.
- Deny by default. The human approves each allowed edit against the task's exact paths. Stop if more scope is needed.
- Never edit this file, D1/D2, permissions, secrets, CI, baseline tests or Git metadata. No shell, external tools, network browsing or delegation.
- Preserve deterministic publication and dispatch authority. Model output is untrusted; report blocked or unsupported cases explicitly.
- Use only synthetic or properly shareable fixtures. Do not place credentials, personal data or raw sessions in public artifacts.
- Ask the human to run tests and provide results. Never invent approvals, transcripts, benchmark scores or passing results.
