# ADR-001 — Deterministic extensions at existing application boundaries

Status: Proposed. Interface version: 1.0.

## Context and drivers

The extension preserves the existing single-stock graph, model clients, data providers and publication paths. Architectural drivers are verifiable outputs, explicit degraded behavior, bounded dispatch, limited baseline changes and independent offline acceptance tests.

## Decision process and alternatives

Trace the existing dispatch and publication paths, compare the candidates in the [evaluation table](../evaluation-table.md), define shared contracts and review adverse cases before implementation.

| Option | Assessment |
|---|---|
| Prompt and configuration changes only | Insufficient enforcement of publication, arithmetic, missing-data state and total request limits |
| Deterministic components at existing boundaries | Selected; supports the five acceptance contracts with localized integration |
| Replacement orchestration | Deferred; increases migration and regression scope without an identified requirement |

## Component decisions

| Requirement | Decision |
|---|---|
| FR-01 | Resolve current-run evidence and apply one publication result at every official sink |
| FR-02 | Compute from validated operands; resolve immutable verified records by ID |
| FR-03 | Separate source coverage, assessment and execution state; 0/3 yields UNKNOWN/null without a sentiment-model call |
| NFR-01 | Atomically reserve capacity at a common outbound boundary |
| NFR-02 | Reduce optional history at the two scoped sites; reject irreducible messages before budget reservation |

Use [C0–C5](../interface-contracts.md) JSON-compatible shared records. Internal types may use adapters. Add separate owner keys to AgentState and retain legacy report strings as views of authoritative records.

## Layered model context

Context layers are role/task identity, standing constraints, typed evidence and run state, active tool exchanges, optional discussion history and the current request. Mark required blocks explicitly.

Assembly order: prioritize and deduplicate optional history; measure the final representation; remove optional groups oldest first; reassemble; re-inject critical constraints; verify required blocks and tool pairs; recount before dispatch. Preserve authoritative stored evidence when reducing a request. Refuse a scoped request when mandatory content cannot fit.

NFR-02 uses a configurable 65536-byte message cap at analyst closure and the neutral risk role. It excludes separately bound tool schemas and is independent of token measurement.

## Token-budget design

The input-token design uses a proposed cap of 16384 tokens and a compaction trigger above 13107 tokens (floor of 80% of the cap). Configure output allowance and provider-envelope reserve independently. Validate the selected model capacity, counting method, schema overhead and provider conversion before enabling this policy. Until then, token enforcement remains unverified. Byte counts are not a substitute for token counts.

## Run profile

The initial product profile uses a configurable request limit of 40, both tiers on the school model alias, explicit thinking-disabled requests and an output allowance of 4096 tokens. NFR-01 boundary fixtures use limit 3. Configuration evidence accompanies baseline comparisons; changes to public semantics require a contract revision.

## Consequences and review triggers

Benefits are localized changes and explicit failure states. Costs are shared dispatch/publication integration and nullable-state compatibility across existing consumers. Review this decision when provider retries become opaque, a sink bypasses publication checks, required context routinely cannot fit, or requirements need different orchestration.

Changes to shared fields, date semantics, thresholds, safety behavior or dependencies require affected-owner review and synchronized requirements, interfaces and tests. Record the human decision and supporting evidence.
