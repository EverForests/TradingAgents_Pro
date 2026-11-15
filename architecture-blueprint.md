# Architecture blueprint

Status: Proposed. Interface version: 1.0. Scope and fit criteria: [D1 registry](docs/req/requirements.yaml). Extend TradingAgents at `upstream-baseline` (`9fa1196fffbcfd9de5146d2dd2869df84ab99838`); retain the single-stock graph, providers, CLI and Python entry points. No brokerage execution, arbitrary prose arithmetic, or new external provider is in scope.

| Requirement | Planned owner module | Contract and authority |
| --- | --- | --- |
| FR-01 / INV-01 | `tradingagents/graph/publication_gate.py` | Build run-local evidence index, validate candidate rating and argument references, and return an approved decision or blocked status/reason. Model text is advisory. Apply the same outcome before CLI/API/report/memory publication. No free-text fallback around the gate. |
| FR-02 | `tradingagents/agents/verified_metrics.py` | Validate provenance, comparable periods, units and operands; produce immutable verified records keyed by metric ID. Resolve controlled fields by ID, not model-supplied values. |
| FR-03 | `tradingagents/agents/sentiment_coverage.py` | Normalize three tool results to coverage, source reasons and nullable score. Report and downstream consume the same state. |
| NFR-01 / INV-02 | `tradingagents/llm_clients/request_budget.py` | Atomically reserve one slot for each in-scope actual send; scope counters per run, including both model tiers. Disable implicit retry for supported course runs. |
| NFR-02 | `tradingagents/llm_clients/context_limit.py` | Prepare final messages for analyst closure and the neutral risk debater; preserve mandatory blocks and reject requests that cannot fit. |

Integrate at existing graph and client seams. At dispatch: prepare final messages → apply context limit where scoped → reserve budget → send. Load existing market and sentiment inputs; attach verified metrics and coverage; run debate and candidate generation; gate candidate before official sinks. Treat any display of intermediate model text as unverified and keep candidate text out of official output on refusal. Historical settlement is outside the metered analysis scope.

Use fixed fixtures and fake transports for deterministic tests, then separately smoke-test configured live integration. Emit run ID, publication status/reason, verified metric counts, sentiment coverage, request count and message byte size without credentials or raw prompts. See [trace matrix](docs/architecture/trace-matrix.md) and [runtime policies](docs/architecture/runtime-policy-catalog.md).

Plan is read-only. A human approves scope, interface and tests before Build starts. A separate reviewer runs verification and records a verdict. Amend D1/D2, tests and governance together when a contract changes; changes to safety enforcement require an ADR and explicit human approval.

## Integration and change control

[C0–C5](docs/architecture/interface-contracts.md) defines shared records, function boundaries, state keys and failure precedence. Each component owns its authoritative records; legacy report strings remain compatible views. Shared-file changes are integrated by the designated coordinator.

The application retains the upstream package layout. Verify the final submission mapping to the required `src/` and `test/` layout before packaging. Approval and outstanding verification items are recorded in [review records](docs/review-memo.md).
