# Product requirements brief

**Target user:** a researcher reviewing a single-stock TradingAgents analysis who needs traceable recommendations, verified selected metrics and predictable model requests.

**Outcome:** extend the pinned baseline so users can trace released recommendations (FR-01), reproduce controlled metrics (FR-02), distinguish no sentiment data from neutral sentiment (FR-03), and bound request count and message size (NFR-01, NFR-02). The release and dispatch guarantees are INV-01 and INV-02.

**Acceptance:** use versioned, shareable offline fixtures and fake model transport for each fit criterion; compare the same fixed input against the baseline when measuring change. Count unfinished runs separately from completed runs. [The product definition](product.yaml) lists product scope; [the registry](requirements.yaml) is the authority for individual thresholds and verification.

**Out of scope:** trading execution, predicting returns, arbitrary narrative arithmetic, new providers, dedicated replay or comparison tooling. The course team approves the requirements, implementation plan and tests before Build.

## Integrated delivery status

The five selected behaviors have executable acceptance evidence in the integrated application at `df8a9d6`, with consolidated records at `b8a7564`. Requirement entries use `verified` for that scoped evidence. The registry revision's historical approval metadata remains separate; implementation evidence does not establish a missing pre-code approval. [Delivery audit](../delivery-readiness.md) lists remaining repository-enforcement conditions.
