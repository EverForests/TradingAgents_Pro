# ADR-001 — Deterministic extensions at existing application boundaries

Current document review: **Approved**, recorded on 21 November 2026. [Offline review record](../../governance/offline-review-20261121.md) distinguishes current acceptance from historical implementation approvals and separate hosted review.

Status: Approved. Interface version: 1.0.

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

## FR-01 reference selection adapter — 19 November 2026

The coordinator requested live verification and repair of long model reference copying on the integrated `77938d0` tree. The recorded AAPL rerun rejected a shortened Bull reference and accepted a complete Bear reference. The earlier blocked AAPL run lacks the manager references needed to establish its exact cause.

Use invocation-local evidence aliases (`E1`, `E2`, ...) and accepted-argument aliases (`A1`, `A2`, ...). Build and freeze the mapping from the menu actually supplied to that invocation. Resolve returned selections to canonical IDs before the existing C1 validators. Keep canonical IDs available for existing callers. Unknown selections remain invalid. Every stored record, candidate and publication chain uses canonical IDs. An alias has meaning only within the menu of its current invocation; ownership continues to be established from full C0/C1 records.

This adapter adds no model request. Diagnostic rejection logs identify the actor and reference without including raw claims or changing public reason codes. Verification must cover both real researcher nodes and the manager, legacy full-ID inputs, unknown/truncated/mixed references, foreign records, missing evidence, deterministic menus and independent mappings across runs. A fixed model replay exercises the revised prompts before delivery. Live provider limitations remain separately recorded.
