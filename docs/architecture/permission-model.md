# Permission model

Default deny for tools, reads and writes. Use three course roles: Plan (read-only), Build (asks on each approved edit), Verify (read-only). The allowlist covers only project governance, the planned implementation seams and course tests. Broad shell/search tools, external directories, MCP and subagents are denied so they cannot replace bounded reads or edits.

| Requirement | Planned edit seam (further narrowed by human approval) |
| --- | --- |
| FR-01 | Publication gate, researcher outputs, decision graph, CLI and report adapters |
| FR-02 | Verified metric owner, fundamentals analyst, state and report adapters |
| FR-03 | Sentiment coverage owner, sentiment analyst, state and report adapters |
| NFR-01 | Budget owner, model factory and approved graph dispatch seams |
| NFR-02 | Context owner, analyst closure and neutral risk role |

Read and edit patterns in [permissions.jsonc](../../.opencode/permissions.jsonc) are authoritative for the tool session. Secrets, project rules, course requirements, existing tests, CI and Git are never agent-editable. Human approves only the exact implementation paths in the plan; do not select an approval that persists beyond the immediate action.

From the repository root, start a clean course session with `OPENCODE_CONFIG="$PWD/.opencode/permissions.jsonc" opencode --pure`. Do not assume this filename is auto-discovered. Before using it, inspect the effective configuration with `OPENCODE_CONFIG="$PWD/.opencode/permissions.jsonc" opencode debug config --pure` locally and check that no merged user/project config grants extra tools or MCP access. Use a clean profile if it does. Verify Plan/Verify deny edits, Build asks for a designated module and denies frozen paths. Do not paste full resolved config into public evidence. This is tool-level enforcement, not an OS sandbox; any failed guard check blocks agent use.
