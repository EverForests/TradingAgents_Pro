# Architecture option ledger

Current document review: **Approved**, recorded on 21 November 2026. [Offline review record](../governance/offline-review-20261121.md) distinguishes current acceptance from historical implementation approvals and separate hosted review.

| Option | Decision and reason | Reconsideration trigger | Evidence |
| --- | --- | --- | --- |
| Prompt-only enforcement | Rejected. Instructions cannot stop an unsupported candidate at every sink or atomically limit concurrent sends. | A requirement becomes presentation-only and requires no deterministic guarantee. | FR-01 missing-evidence counterexample; C4 race tests. |
| Replace the upstream orchestration | Deferred. It would migrate working providers, graph consumers and memory without a selected requirement needing replacement. | Existing seams prevent a required contract or create measured maintenance cost exceeding migration cost. | ADR-001 and integrated dispatch checks. |
| Issue evidence IDs in model text | Rejected as an authority mechanism. Models may select a reference, while deterministic code owns records and acceptance. | Never for publication authority; model formatting can evolve behind C1. | Foreign-reference tests and retained-material checks. |
| Require models to copy only canonical long IDs | Replaced by invocation-local selections with canonical compatibility. Long strings caused an observed rejected reference. | Alias scope or provider structure changes, or a new collision counterexample appears. | 20 reference-adapter cases; real-data DeepSeek replay. |
| Treat missing sentiment as a neutral score | Rejected. It confuses absence of evidence with a measured outcome. | No automatic reconsideration; changing the product meaning requires an explicit requirement revision. | Paired 16-case comparison preserves 11 valid neutral controls. |
| Enforce a global token limit using byte counts | Rejected. UTF-8 bytes and model tokens measure different representations. | A validated tokenizer/capacity policy supports separate enforcement. | C5 scope and ADR token-budget design. |
