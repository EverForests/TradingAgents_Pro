# Permission model

Current document review: **Approved**, recorded on 21 November 2026. [Offline review record](../governance/offline-review-20261121.md) distinguishes current acceptance from historical implementation approvals and separate hosted review.

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

## Configuration review items

The documentation index (`docs/README.md`), product scope (`docs/req/product.yaml`) and review memo (`docs/review-memo.md`) have exact read-only allowlist entries. C0–C5 is covered by the existing architecture Markdown read pattern.

The AI-use log, bug and debt records, upstream vendor/date adapters and non-Python fixtures are not generally allowlisted. Before a task depends on one, the human maintainer must review its exact path and update both configuration copies consistently if access is needed. Do not add a broad `docs/**`, vendor-tree or repository-wide write rule.

The integrated allowlist includes the approved source and test seams from all five features, including the read-only reference `tests/test_graph_end_to_end.py`. An entry grants only its declared action. New dependency reads and fixture paths still require exact-path maintenance; reading a reference test never grants permission to edit it.

Configuration changes belong to the human maintainer. Record effective guard-probe outcomes before session use. If a required read is denied, stop the affected operation for exact-path review. Tool boundaries and evidence responsibilities are defined in the [tool manifest](../code-governance/mcp-tool-manifest.md).

## Integrated configuration snapshot — 20 November 2026

The effective configuration and course copy are byte-identical. They contain 99 allow rules within the default-deny policy. Plan and Verify remain read-only; Build edits remain subject to exact reviewed task scope and interactive approval. This is a configuration-source observation, not a new runtime guard probe. Historical role probes remain attributed to their original sessions.

The assigned peer-review ring does not widen agent authority. EverForests controls integration and merge; the owners and reviewers are listed in the document index. Supporting automation tools do not convert a denied OpenCode action into a permitted one or constitute a human approval.
