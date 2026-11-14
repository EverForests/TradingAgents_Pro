# Permission model

Default deny for tools, reads and writes. Use three course roles: Plan (read-only), Build (asks on each approved edit), Verify (read-only). The allowlist covers only project governance, the planned implementation seams and course tests. Broad shell/search tools, external directories, MCP and subagents are denied so they cannot replace bounded reads or edits.

| Requirement | Planned edit seam (further narrowed by human approval) |
| --- | --- |
| FR-01 | Publication gate, researcher outputs, decision graph, CLI and report adapters |
| FR-02 | Verified metric owner, fundamentals analyst, state and report adapters |
| FR-03 | Sentiment coverage owner, sentiment analyst, state and report adapters |
| NFR-01 | Budget owner, model factory and approved graph dispatch seams |
| NFR-02 | Context owner, analyst closure and neutral risk role |

OpenCode 2.3.0 automatically loads [opencode.jsonc](../../.opencode/opencode.jsonc). It is the source of truth; [permissions.jsonc](../../.opencode/permissions.jsonc) is its identical course-delivery copy, not a second configuration source. Keep them identical (`git diff --no-index .opencode/opencode.jsonc .opencode/permissions.jsonc`). Secrets, project rules, course requirements, existing tests, CI and Git are never agent-editable. Human approves only the exact implementation paths in the plan; do not select an approval that persists beyond the immediate action.

From the repository root, run `opencode --version`, `opencode debug config` and `opencode debug agents` before starting `opencode`. Verify the project config source, both rule files, and the three course roles. V2 does not use the previous `--pure` workflow: inspect configured plugins and MCP tools separately, and use a clean profile if unrelated integrations or overrides remain.

In a disposable checkout, check that Plan/Verify can read a whitelisted file but cannot edit it; all three roles must deny shell and external access. Build must ask before editing a designated module and deny a frozen path such as `AGENTS.md`. Decline the probe edit. Confirm the guard outcomes in the actual tool session; config discovery alone is not enforcement evidence. Do not publish config dumps. These are tool-level controls, not an OS sandbox; any failed guard check blocks agent use.

See the [team operation manual](../operation-manual.md) for the full Plan → Build → Verify workflow.
