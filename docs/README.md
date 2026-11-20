# Course deliverable index

This index describes the integrated TradingAgents Pro delivery. The upstream reference is `9fa1196fffbcfd9de5146d2dd2869df84ab99838`. The verified application and tests are at `df8a9d6419dfa0aab2f4d8986d0a44060354cdb9`; consolidated online evidence is recorded at `b8a7564ed9c2ac82d0bab92f548bbe6daea763f3`. Document preparation on 20 November 2026 does not change either executable revision.

| Deliverable | Authoritative artifacts |
| --- | --- |
| D1 Requirements | [Product PRD](req/product.yaml), [registry](req/requirements.yaml), [schema](req/req-schema.json), [AI-use log](ai-use-log.yaml) |
| D2 Architecture | [Blueprint](../architecture-blueprint.md), [ADR](architecture/adr/001-choice-tbd.md), [contracts C0–C5](architecture/interface-contracts.md), [invariants](architecture/invariants.md), [trace matrix](architecture/trace-matrix.md), [memory/state](architecture/memory-design.md), [permissions](architecture/permission-model.md), [runtime policies](architecture/runtime-policy-catalog.md), [candidate evaluation](architecture/evaluation-table.md), [evaluation logbook](architecture/evaluation-logbook.md), [risks](architecture/risk-list.md), [options](architecture/option-ledger.md) |
| D3 Coding governance | [AGENTS.md](../AGENTS.md), [structural constraints](code-governance/structural-constraints.md), [tool manifest](code-governance/mcp-tool-manifest.md), [effective configuration](../.opencode/opencode.jsonc), [course copy](../.opencode/permissions.jsonc), [standing rules](../.opencode/rules.md), [covenant](../.agent/rules.md) |
| D4 Verification governance | [Verification rules](code-governance/verification-constraints.md), [review memo](review-memo.md), [debt register](debt-register.md), [bug diary](bug-diary.md), [live acceptance](live-acceptance.md) |
| D5 Annotated sessions | [Complete transcript index](../transcripts/README.md); five redacted annotated transcripts and source derivatives |
| D6 Process report | [Report.md](../Report.md), including GitHub collaborators, contribution weights and reflections |
| D7 Repository and CI | [README](../README.md), [workflow](../.github/workflows/ci.yml), [gate audit](delivery-readiness.md#d7-gate-audit) |
| D8 Source and tests | `tradingagents/`, `cli/`, `tests/`, `test/offline/`, `test/live/`; [source packaging map](../src/README.md) |
| D9 Static launch prompt | [Prompt.md](../Prompt.md) |

## Ownership and review

| Requirement | Owner | Assigned peer reviewer |
| --- | --- | --- |
| FR-01 / INV-01 | EverForests | asling3 |
| FR-02 | KyrieT331 | EverForests |
| FR-03 | wmq12138 | KyrieT331 |
| NFR-01 / INV-02 | majiaqi-yan | wmq12138 |
| NFR-02 | asling3 | majiaqi-yan |

After peer acceptance, coordinator EverForests controls integration and merge. A role assignment, a private plan approval, a feature verdict and a submitted GitHub Review are distinct records. [Review evidence](review-memo.md#delivery-reconciliation--20-november-2026) identifies their provenance. Team-agreed relative contribution is 1.00 per member, or 20% each. No hours are claimed.

## Reproduction and delivery

Use the [repository instructions](../README.md) for installation, deterministic tests and separately authorized live checks. The final report retains historical outcomes with their revisions. Test counts from overlapping feature groups are never added together. A completed run can remain blocked, and publication approval does not establish investment correctness.

The coordinator selected de-identified public publication on 20 November 2026. The public repository uses GitHub collaborators and redacted existing D5 evidence. The restricted submission retains student numbers and full originals. Credentials, account state and runtime caches remain excluded. Presentation and packaging derivatives remain outside the source repository. Narrative documentation is English. Supporting automation is described as automation tools, while original evidence remains unchanged. [Delivery audit](delivery-readiness.md) records remaining enforcement limits without converting them into passes.
