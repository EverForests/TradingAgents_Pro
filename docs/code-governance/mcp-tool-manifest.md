# MCP tool manifest

No MCP server is needed or approved for Plan, Build or Verify. Do not enable user/global MCP servers for this project session. Application model and data providers are runtime dependencies, not tools granted to coding agents.

| Role | Allowed local tools | Denied |
| --- | --- | --- |
| Plan | Read whitelisted governance and integration files | Edits, shell, delegation and network tools |
| Build | Same reads; ask for each whitelisted source or course test edit after plan/test approval | Shell, Git operations, unrestricted writes, MCP and network tools |
| Verify | Same reads; inspect diffs and human-supplied command results | Edits, shell, delegation and network tools |

The human runs test commands, controls Git, and records approvals and results. See the [permission model](../architecture/permission-model.md) for launch and verification.

## Other assistants

Codex may assist human analysis and document review; this is not evidence that the teacher has accepted it as a replacement for the OpenCode implementation workflow. Record the real tool used. OpenCode policy does not constrain another assistant automatically. Do not delegate forbidden shell, network, edits or approval decisions to a second assistant as a workaround. Human-controlled Git/test operations and course-agent operations remain distinct in the evidence.
