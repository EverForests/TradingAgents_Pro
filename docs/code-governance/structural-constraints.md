# Structural constraints

Extend the baseline; do not replace the graph, CLI, providers or package layout. The blueprint assigns exactly one owner module to each new design element. Existing modules remain integration adapters; do not duplicate business rules across CLI, API and reports.

| Requirement | Owner and boundary |
| --- | --- |
| FR-01 / INV-01 | Publication gate owns the official outcome; pass its result to all sinks, including memory. |
| FR-02 | Verified metrics owns arithmetic and reference resolution. Downstream renders resolved values. |
| FR-03 | Sentiment coverage owns missingness and reasons. Consumers do not invent numeric defaults. |
| NFR-01 / INV-02 | Request budget owns the atomic run counter. Only a reserved dispatch may send. |
| NFR-02 | Context limit owns payload sizing and deterministic reduction; it cannot bypass the budget or remove mandatory content. |

For each new or modified module and function, document the associated requirement, ADR and invariant where applicable in a short comment or docstring. Integration code may orchestrate but cannot override an authoritative rejection. Preserve stable baseline behavior outside approved scope; do not add providers, packages or cross-layer imports without architecture review.

## Contract ownership before parallel Build

Use [C0–C5](../architecture/interface-contracts.md) for common records and failure meanings. The team must name a shared-file integration owner and exact paths for state/schema, reporting and dispatch changes. Each feature may use an approved fake producer/consumer for independent tests; integration tests must later replace those doubles with real connected components. Do not treat a mock-only pass as proof that the integrated graph satisfies the contract.
