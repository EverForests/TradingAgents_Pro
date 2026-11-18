# TradingAgents Pro — CS5351 Project Report

| Field | Value |
| --- | --- |
| Course | CS5351 Agentic Software Engineering |
| Deliverable | D6 project report |
| Status | Team review draft |
| Repository | [EverForests/TradingAgents_Pro](https://github.com/EverForests/TradingAgents_Pro) |
| Upstream reference | `upstream-baseline` at `9fa1196fffbcfd9de5146d2dd2869df84ab99838` |
| Integrated revision under test | `e6b60563161e3e5035bdf95fff52b5912d5aeaa9` on `integration/course-project`, associated with [integration PR #11](https://github.com/EverForests/TradingAgents_Pro/pull/11) |
| Evidence date | 18 November 2026 |

## 1. Project summary

TradingAgents Pro extends an existing multi-agent application for single-stock analysis. The upstream workflow collects market, news, sentiment and fundamental information, passes analyst results through research and risk discussions, and produces a candidate recommendation. The project improves how that workflow handles evidence, numerical claims, missing data and model requests. It retains the upstream graph, command-line and Python interfaces, reporting functions and data providers. Brokerage execution and portfolio performance evaluation are outside the project scope.

The five requirements address different failure modes. FR-01 gives a deterministic gate authority over the publication of recommendations. FR-02 recomputes specified numerical metrics from attributed operands. FR-03 records which sentiment sources have usable data and represents missing sentiment explicitly. NFR-01 bounds the number of model requests per analysis. NFR-02 bounds the serialized message size at two defined points in the workflow. Together, these controls cover the inputs the model receives, the claims other stages can reuse, the requests the system can send and the candidate it can publish.

A coordinated integration was necessary because the feature branches touched shared graph state and request boundaries. Individual module tests showed that each mechanism could work in isolation. The combined workflow also had to demonstrate that a budget refusal suppressed publication, a context refusal left the budget unchanged, and absent sentiment neither created publication evidence nor blocked otherwise valid market analysis. Cross-feature tests exercised those interactions through the integrated application.

The integrated offline verification recorded **1,812 passing tests, zero failures, one skip, one deselection and 100 passing subtests**. A separate live run used the school-hosted DeepSeek model and external data. It confirmed that a one-request budget stopped the analysis after one observed model HTTP attempt, and that an analysis could complete with missing sentiment while the publication gate withheld the candidate. A live check independently reproduced a revenue calculation from SEC data. Yahoo Finance access prevented the team from obtaining the market evidence needed for a live approval example. The deterministic approval example and the live evidence-shortage example remain distinct pieces of evidence. [Integrated verification record](docs/review-memo.md) · [Integrated course run instructions](README.md#integrated-course-run)

## 2. Requirements discovery and scope control

### 2.1 Starting point

The team fixed an upstream Git revision and used it to separate existing behavior from changes introduced by the project. The reference tree supplied the analyst graph, model and vendor clients, CLI, reporting, decision memory and upstream regression suite. Recording the revision made it possible to return to the same implementation for counterexamples and to compare selected behavior under controlled data and model responses. It also reduced the risk of interpreting a change in the upstream repository as an improvement or defect in the course project.

Requirement discovery used teammate reports, sample outputs, baseline source inspection and focused experiments. The resulting observations had different evidential strength. One report presented a neutral sentiment score while describing all three sources as unavailable. Source inspection identified a corresponding representational constraint in the upstream schema, which required a numeric score and lacked an explicit unknown band. Several reported arithmetic discrepancies motivated independent calculation, but the underlying operands and fiscal periods still needed to be identified before each example could become a reproducible acceptance case. Large analyst and risk prompts motivated a size constraint, while reported request counts helped identify possible pressure on cost. These observations guided the initial design and were preserved with their provenance. [Source register](docs/review-memo.md#source-register) · [Bug diary](docs/bug-diary.md)

The team selected five requirements with separable responsibilities and measurable outcomes. Each owner could develop against a common set of interfaces while the coordinator reserved responsibility for shared integration points. This division made small feature branches practical and made the remaining interactions visible early. In particular, a verified financial value and an accepted publication citation are separate records with separate owners. Likewise, a request that cannot fit within the prepared context has to be rejected before the request-budget owner reserves a slot.

### 2.2 Selected requirements

| ID | Target behavior | Fit criterion used in the project | Scope decision |
| --- | --- | --- | --- |
| FR-01 / INV-01 | Publish a legitimate candidate with a resolvable chain from an accepted argument to evidence from the same run. | A positive candidate can publish. Invalid ratings and missing, unknown or foreign references are blocked. Rejected candidates produce zero official releases or decision-memory entries in the acceptance fixtures. | Reference integrity and the official output boundary. |
| FR-02 | Recompute agreed growth rates, ratios and signed differences from recorded operands. | Compare against frozen values within the D1 tolerances. Reject invalid provenance, identity, units, periods or numerics. The same verified metric is referenced by downstream fields and the report. | Named formulas and controlled fields. |
| FR-03 | Report evidence coverage and assessment separately for news, Stocktwits and Reddit. | Zero valid sources yield `NO_DATA / UNKNOWN / null` and zero sentiment-model calls. One or two sources yield partial coverage. Three valid sources yield full coverage. Supported neutral assessments remain valid. | Data availability and assessment semantics. |
| NFR-01 / INV-02 | Enforce a shared limit on in-scope requests from both tiers and across parallel graph workers. | In the boundary case a flow that needs four requests and has a limit of three sends exactly three. The fourth attempt is refused and the run emits no official rating. | Actual model requests in the metered analysis. |
| NFR-02 | Bound the final message representation at analyst wrap-up and the neutral risk debater. | Configured tests enforce 65,536 serialized UTF-8 bytes and preserve every required block on successful preparation. Irreducible input produces `CONTEXT_TOO_LARGE` with no reservation or send. | Scoped message bytes, with a separate token design in D2. |

[D1 requirements registry](docs/req/requirements.yaml) · [D4 verification rules](docs/code-governance/verification-constraints.md)

### 2.3 Ambiguities resolved during specification

FR-01 required the team to define what the system was publishing. An analyst narrative, a Portfolio Manager candidate, an execution status and an official rating can all exist in a run. C1 assigns publication authority to a single deterministic result. A candidate may be visible to the internal graph for validation, while the CLI, Python API, saved official report and decision memory consume the gated result. The run may complete normally and still be denied publication. That distinction governs the interpretation of the live runs.

For FR-02, “price difference” originally left room for an absolute difference, a reversed subtraction or the use of rounded display values. The clarified AAPL example fixes the role of each operand. Subtracting the closing price from the Bollinger upper band produces the positive case, and exchanging the operands changes the sign. The annual growth example specifies the Cost of Revenue field and comparable fiscal years. The calculation tolerance applies only after the field, currency and period have been matched and the operand precision recorded.

FR-03 separates three questions that the upstream user interface tended to combine. How many sources provided valid observations? Did the assessment process obtain a usable result? If so, what was the measured sentiment? A genuine neutral score belongs to the third question. An unavailable source belongs to the first. When coverage or assessment fails, downstream state can now express the distinction explicitly and carry the corresponding reasons.

For the two performance requirements, “call” became an outbound attempt within the metered analysis, and “context size” became the measured serialized message array in the defined scope. A loop iteration, a tool lookup and an outbound model request can have different counts. An application retry that sends another request consumes another slot. Separately bound tool schemas and model-token capacity are outside the NFR-02 byte metric. These definitions made it possible to design tests at the points where the system actually sends and publishes. [C0–C5 interface contracts](docs/architecture/interface-contracts.md)

## 3. Architecture and trade-offs

### 3.1 Alternative designs

The team compared prompt and configuration changes, deterministic components at existing boundaries, and a replacement orchestration layer. Prompt changes could improve instructions, presentation and model cooperation. They could not enforce what happened after an invalid response or count outbound attempts when more than one graph worker dispatched concurrently. An orchestration replacement could centralize state from the outset, with the cost of migrating the graph and every affected consumer and then re-establishing baseline behavior.

The selected design adds deterministic components at existing seams. It keeps upstream execution paths recognizable while introducing a clear authority for each new record. The trade-off is that compatibility and integration must be tested carefully. A single adapter can work in isolation while a caller still reads a legacy field, remints run identity, bypasses dispatch or loses an authoritative record across the subgraph boundary. The architecture therefore maps each requirement to its owner module, shared state and executable acceptance evidence. [Architecture blueprint](architecture-blueprint.md) · [ADR-001](docs/architecture/adr/001-choice-tbd.md) · [Candidate evaluation](docs/architecture/evaluation-table.md)

### 3.2 Runtime data flow and authority

The graph creates a shared run context with the run identity, normalized ticker, effective analysis date, execution status and request limit. Analysts collect source data using the inherited tools. A successful verified market snapshot can be retained with a content reference and associated with that run. Eligible numerical operands go through the verified-metric producer. Sentiment collection emits source results and a coverage assessment. Debate and risk analysis consume the results for their intended purposes, and the Portfolio Manager produces a candidate for the final gate.

The project treats provider data, model prose and deterministic records differently. The raw source remains the basis for traceability. A model may propose an argument or select an identifier. The evidence registry and gate check identity, provenance fields, reference resolution and admissibility. The numeric registry computes and exposes a verified result only for supported operators and valid operands. A generated explanation can accompany the result. The official state and report fields derive their values from the records.

Publication then uses one result for each official consumer. A blocked candidate is omitted from the formal decision and the decision memory, while diagnostics can explain the application state. This preserves visibility into incomplete runs and evidence shortages without presenting the candidate as authorized. Run-local references include enough identity for a second analysis of the same stock and date to remain separate. Retained evidence that can no longer be resolved cannot authorize publication. [Invariant register](docs/architecture/invariants.md) · [Memory and state design](docs/architecture/memory-design.md)

### 3.3 Model-request flow

NFR-02 executes before NFR-01 at a scoped dispatch site. The application assembles the final request, measures its canonical UTF-8 representation and removes eligible optional groups when needed. Required instructions, task identity, authoritative evidence and tool exchanges have to remain coherent. Both sides of a tool call and its result are retained together. When an adapter represents tools as text, their names, arguments and outcomes remain associated. The reducer is deterministic for equivalent inputs.

Once a request is eligible to send, the client reserves capacity against the run's shared budget. The accounting boundary records the outbound attempt, including an attempted request whose delivery becomes uncertain. Successful response receipt is a separate observation. In-scope application retries can send only if another slot is available, and the metered profile disables automatic SDK retries. The application maps budget and context refusals to typed execution outcomes. These outcomes reach the publication gate, which withholds the official decision.

The proposed D2 token policy and the implemented byte check have separate acceptance conditions. ADR-001 proposes a 16,384-token cap and a compaction trigger above 13,107 tokens. Provider tokenizer behavior, model capacity and schema overhead still require validation before treating that proposal as enforcement. The verified NFR-02 statement is the byte bound at the scoped request sites. The deployed product profile also has a configured call limit. Its live diagnostic overrides are recorded per run to avoid mistaking test inputs for product defaults. [ADR-001 context design](docs/architecture/adr/001-choice-tbd.md#layered-model-context) · [Runtime policies](docs/architecture/runtime-policy-catalog.md)

## 4. Supervised development process

### 4.1 Common document baseline and feature ownership

The team first established a shared document baseline on `feat/course-deliverables`. This branch contained the project scope, requirement registry, architecture rationale, governance files and test strategy. Requirements then proceeded in separate feature branches. The common contracts made it possible for owners to develop against the same interpretation of execution, publication, evidence, coverage, budget and context. The parent revision remained in each feature record so reviewers could identify which baseline its design and tests assumed.

The coordinator accepted FR-01 from PR #4, FR-02 from PR #8, FR-03 from PR #6, NFR-01 from PR #7 and NFR-02 from PR #10 for local integration. PR #10 superseded PR #9. The integration history incorporated the five reviewed heads and gave the coordinator responsibility for the shared graph and client changes where the feature diffs intersected. Results quoted by PR authors were retained as feature-stage evidence. The combined checkout was measured independently because a Git merge and a successful owner-module test can leave behavioral conflicts at shared boundaries. [Feature PR intake](docs/review-memo.md#feature-pr-intake--2026-11-18)

### 4.2 Plan, Build and Verify

The course OpenCode workflow used a read-only Plan role to locate entry points and propose exact implementation files, test cases, expected failures, dependency requirements and rollback steps. Planning tied each proposed change to a requirement and the applicable shared contract. A plan could be revised when inspection exposed a missing caller or an ambiguous behavior. The team distinguished a plan/test approval from a later review of implemented changes and from the decision to integrate a branch.

Build followed the agreed scope. The test-first structure required at least one independent adverse case for important behavior. For example, an invalid candidate should produce an observable publication outcome and leave no decision-memory entry. A test for this behavior needs to reach the real consumer path with controlled model and data inputs. A failure caused by missing imports, unsupported test setup or an incomplete stand-in reveals a test problem, so it cannot establish the claimed product defect.

Verify reviewed the implementation and assertions against the specification and reported what it could inspect. Where the role could read code but could not run commands, the terminal receipt supplied the executable result. A read-only opinion and a test run have distinct provenance. The review memo preserves the reviewed revision, source of approval evidence, unresolved items and verdict when one exists. The record of local integration authorization on 18 November applies to that specific operation. Feature approvals and GitHub review evidence need their own records. [Launch prompt](Prompt.md) · [Permission model](docs/architecture/permission-model.md) · [AI-use log](docs/ai-use-log.yaml) · [Review memo](docs/review-memo.md)

### 4.3 Permission changes as maintained artifacts

The file allowlist required explicit reads and writes for the task role. Early sessions exposed a practical weakness of a restrictive policy. A planner could read integration code yet be denied a related contract or test that defined the boundary. For example, `tests/test_graph_end_to_end.py` contained a fixed-data workflow useful to the FR-02 owner. The maintainers granted the exact read permission and synchronized the active OpenCode configuration with the course permissions copy.

The repair made the allowed planning activity expressible without widening edit permission. It also showed that a permission model must co-evolve with its referenced files and test obligations. Reporting a denial gave the maintainer a concrete missing capability. Updating both copies and checking parity in CI reduced the chance that an agent would run under a different policy from the one shown in the deliverable. Separate writable paths still depended on the approved task scope. [OpenCode active configuration](.opencode/opencode.jsonc) · [Course permissions copy](.opencode/permissions.jsonc) · [Permission review evidence](docs/bug-diary.md)

## 5. Implementation and integration findings

### 5.1 FR-01 — Evidence and publication

The evidence collector records a successful verified snapshot as retained material with a source locator, date window and current-run identity. The researchers can cite those IDs in structured arguments. The system validates the citations before admitting an argument. The candidate then refers to accepted argument IDs. The gate resolves the argument and underlying evidence again, including the stored content reference, before returning approval. This second check matters because a stale, missing or foreign record may appear syntactically valid.

Initial acceptance focused on a Buy candidate without evidence. The API and memory checks were separate so a failure in one could not conceal the other. Later controls included legal ratings with real run-local references, unknown references, cross-run references, retained material that no longer resolves and failure states that should suppress an otherwise plausible decision. CLI layout snapshots exercised real rendering with a substitute graph and the real publication gate. The Python graph tests separately exercised the real graph with controlled inputs. These layers cover different paths and are reported with their respective scopes.

A later C0/C1 alignment made the shared `PublicationResult` authoritative. The combined tests observed that a blocked execution could not become official through a direct reporting or memory path. Positive verification followed the chain from the candidate to the accepted argument and source material. The current live market evidence collector uses the Yahoo-backed verified snapshot path. SEC-derived metric records created by FR-02 do not automatically become FR-01 evidence. [Publication gate](tradingagents/graph/publication_gate.py) · [Evidence collector](tradingagents/agents/evidence_collection.py) · [Positive publication test](test/offline/test_fr01_publish_valid.py)

### 5.2 FR-02 — Verified metrics

FR-02 supports selected growth rates, ratios and signed differences. Each formula has explicit operand roles, unit and period constraints. The recorded operands identify their sources and preserve their computation precision. The producer returns an immutable verified metric with its identifier, or `UNVERIFIABLE` when the inputs cannot support the claim. The downstream consumer and the final table resolve the stored metric by identifier. This guards against a model silently changing a value when repeating it.

The signed AAPL example illustrates why the formula and data provenance are both necessary. The retained demonstration uses a Bollinger upper band of 352.771 USD and a close of 348.245 USD. Upper band minus close yields +4.526 USD, and reversing the roles yields −4.526 USD. That pair detects a reversed operand and an accidental absolute value. A separate problem appeared in a clean install, where a dependency version changed how the Bollinger band uses standard deviation. Reproducing the mismatch established that the approved operand calculation depended on the dependency version. The integrated branch constrains `stockstats` to versions at least `0.6.5` and below `0.6.14`. Verification used `0.6.13` for the sample-standard-deviation calculation.

The financial fixtures cover the expected NVDA revenue growth, AAPL Cost of Revenue growth and MSFT capital expenditure ratio. The controlled examples show that the formulas can reproduce the specified values and reject bad operands. Source-specific evidence remains attached to each example. For instance, the archived AAPL price snapshot gives historical source evidence, while a fresh online reproduction requires a new accessible market snapshot. [Verified metric tests](test/offline/test_verified_metrics.py) · [Operand notes](docs/code-governance/verification-constraints.md#fr-02-aapl-acceptance-examples)

### 5.3 FR-03 — Sentiment coverage and assessment

FR-03 records three logical sources and evaluates whether their individual responses are attributable to the ticker and requested period. Missing data, malformed responses and valid neutral evidence have different outcomes. With no valid source, the sentiment path generates an explicit missing assessment and skips its model call. With useful observations, the assessment path can still represent neutral sentiment. The rest of the graph can use market and financial data even if sentiment is unknown.

The module tests exposed cases that a simple nonempty-content check would miss. Error or blank bodies could arrive with plausible metadata. A very large score could overflow during conversion before the range check ran. A broad placeholder filter could reject a genuine headline, while equivalent ticker forms could cause correct material to fail attribution. The repairs validated response shapes and score bounds and restricted empty-marker handling to the expected provider form. The matched upstream comparison then checked both adverse and legitimate neutral cases under controlled inputs.

Integration exposed an additional issue. The sentiment node produced the authoritative record, but the subgraph failed to return it to the graph that supplied downstream prompts. A test with the real market-plus-social graph demonstrated the loss and checked the repaired handoff. The combined positive case retained `NO_DATA / UNKNOWN / null` for the sentiment assessment while still allowing a valid market-evidence decision. [FR-03 handoff](docs/fr03.md) · [Paired comparison](test/offline/test_fr03_paired.py)

### 5.4 NFR-01 — Shared outbound budget

The budget module uses atomic reservation per run. A reservation protects scarce capacity while multiple callers prepare to send. Cancellation can release a reservation when the transport has not started. Once an outbound attempt occurs, an uncertain delivery result remains counted. This distinction is important in a race and in failure handling. If a limit of three is reached, a fourth request must be refused even when the result of a previous attempt could not be established.

The owner initially verified the module with a fake transport and a last-slot race. Module review identified the integration conditions needed to enforce the requirement at runtime. These included wiring both model tiers to the metered path, preventing SDK retries, preserving the counter across graph workers and ensuring the refusal reached execution status and publication. In the integrated SDK transport fixture, a flow with limit three originally emitted four sends. After integration, it permitted the three requested attempts and refused the fourth. The verification also covered independent runs, parallel analysts, streaming and provider failures.

Historical settlement is outside the metered analysis scope. Metered checkpointing is refused in the tested course profile. A future metered resume feature would need to preserve the charged count, since creating a new counter for the same run would undermine the invariant. The project separately tested ordinary graph evidence identity on its supported checkpoint path. [Budget module](tradingagents/llm_clients/request_budget.py) · [Budget tests](test/offline/test_request_budget.py) · [Integrated dispatch tests](test/offline/test_integration_dispatch.py)

### 5.5 NFR-02 — Scoped context preparation

The input control first measures the prepared messages for analyst wrap-up and the neutral risk debater. The implementation removes eligible optional history in deterministic order. The test suite covers short requests, inputs that can be reduced, irreducible required content, multibyte strings and complete tool-call pairs. A count in bytes is deliberately sensitive to multibyte content. Verification also checks the final message array at dispatch in the metered profile, since encoding and conversion occur after parts of the application assemble their messages.

The joint C4/C5 test is central to the integration evidence. It makes required content too large and asserts that the terminal result is `CONTEXT_TOO_LARGE` with no budget reservation and no provider attempt. An exception after the client sends would satisfy neither the context requirement nor the correct budget behavior. The test checks both sides of that failure boundary. Similarly, a provider payload test verifies the configured DeepSeek alias and explicit disabled-thinking setting on both tiers. [Context implementation](tradingagents/llm_clients/context_limit.py) · [Integrated dispatch tests](test/offline/test_integration_dispatch.py)

## 6. Verification and results

### 6.1 Verification design

The team used structural, regression and behavioral checks. Structural checks inspect the module boundaries, dependency consistency, requirements schema, references, permission copies and lint. Regression checks execute the upstream suite alongside the accumulated course tests. Behavioral checks exercise known positive cases and meaningful counterexamples through the relevant owner and integration boundaries. The fixed upstream tree is used in the paired FR-03 comparison so changes in source data or model output do not confound the observation.

The test plan separates field-level rules from observable effects. It can test a registered argument in isolation, then check what the real Python API returns and what decision memory retains. It can verify a budget primitive and separately instrument the HTTP boundary to count sends. It can validate a coverage record and then test whether the graph delivers it to the right downstream prompt. This arrangement gives a failing integration test a narrower diagnosis while preserving confidence that the owner-module behavior is reachable through normal entry points.

The integrated run used Python 3.13.3 and `stockstats 0.6.13`. It combined `tests` and `test/offline` and included the 33 paired FR-03 assertions. The loopback callback test ran with proxy bypass for `127.0.0.1` and `localhost`. The local acceptance receipts retain the exact invocation, pinned comparison tree and JUnit result. The optional Bedrock dependency accounted for the one skip. A test requiring the real DeepSeek API accounted for the one deselection. [D4 verification rules](docs/code-governance/verification-constraints.md) · [Trace matrix](docs/architecture/trace-matrix.md) · [Integration review](docs/review-memo.md)

### 6.2 Integrated offline results

| Area | Observed result | Supported conclusion |
| --- | --- | --- |
| Entire offline regression | 1,812 passed, 0 failed, 1 skipped, 1 deselected, and 100 passing subtests | The tested integrated revision passed the recorded regression under the stated environment and exclusions. |
| FR-01 / INV-01 | 110 passing cases grouped with FR-01 | Valid evidence can authorize a decision. Invalid candidates, foreign references and incomplete executions are refused. Tested official consumers suppress rejected ratings. |
| FR-02 | 48 passing feature cases | The supported formulas, signed difference, record identity and rejection rules behave as specified for controlled operands. |
| FR-03 | 159 passing cases grouped with FR-03 | Missing source coverage and valid neutrality are distinguishable. The graph can proceed with other evidence when sentiment is unknown. |
| NFR-01 / INV-02 | 39 budget module cases and cross-feature dispatch checks | A shared quota bounds actual transport attempts in the tested course profile, including contention and limit exhaustion. |
| NFR-02 | 37 context cases and cross-feature dispatch checks | Scoped message preparation preserves required context and refuses irreducible messages before a reservation or provider send. |
| Shared integration | 7 tests in the integrated dispatch file | The tests cover real graph and client boundaries with controlled model, data and transport behavior, including request shape for the school-provider profile. |

The feature rows group related tests from the combined run, with some upstream and shared cases testing more than one behavior. The isolated owner-module counts are retained for their original revisions. The read-only verification sessions checked which source and assertions supported each fit criterion. The pass counts are drawn from the actual terminal run. [Integrated review and verification](docs/review-memo.md) · [Integrated dispatch tests](test/offline/test_integration_dispatch.py)

### 6.3 Live DeepSeek and provider checks

The live cases analyzed NVDA as of 10 November 2026. They used the market, social, news and fundamentals analysts, isolated caches, empty decision memory and the school-hosted `CS5351/DeepSeek-V4-Flash` alias for both model tiers. The application instrumented the HTTP transport to count model attempts. Testing used the same integrated revision as the offline acceptance. Each case has a separate execution and publication outcome.

| Case | Request limit | Observed model HTTP attempts | Execution and publication |
| --- | ---: | ---: | --- |
| Low budget | 1 | 1 | `BUDGET_EXHAUSTED` and `BLOCKED / BUDGET_EXHAUSTED`. |
| Initial normal run | 40 | 11 | `FAILED` and `BLOCKED / RUN_NOT_COMPLETE`. The first receipt did not capture the underlying transport exception type. |
| Diagnostic rerun | 29 | 22, all HTTP 200 | `COMPLETED` and `BLOCKED / INSUFFICIENT_EVIDENCE`. Diagnostic reports were retained. |

None of these cases recorded an official rating, official decision file or new decision-memory entry. The low-budget case supplies live evidence of early refusal at the configured request ceiling. The diagnostic rerun shows that the model requests can succeed and the analysis can finish while publication is withheld. It also recorded zero of three valid sentiment sources and returned `NO_DATA / UNKNOWN`. Per-node model-call behavior for the zero-source case is verified by the offline fixtures.

The diagnostic rerun reported 16 verified metric rows. An independent check of the downloaded SEC Company Facts data used two complete quarterly `Revenues` values from NVDA accession `0001045810-26-000075`. The values were 96,221 million USD and 46,743 million USD. The calculation `100 × (96221 / 46743 − 1)` gives approximately 105.85114349%, consistent with the recorded metric. This is an online provenance and formula check for that metric. The AAPL market-derived price difference was not reproduced in this live series.

The initial market-snapshot preflight received a Yahoo connection error and produced no evidence. A later connectivity check reached both Yahoo chart endpoints and received HTTP 429 responses. The project's snapshot tool then used temporary caches and its standard backoff, exhausted three retries, and returned `DATA_UNAVAILABLE` with zero retained evidence records. No model requests were made during the preflights. A live `COMPLETED / APPROVED` example on the integrated application remains unverified. The live receipt also lacks per-request message-size measurements, so the NFR-02 boundary claim rests on the offline tests. [Integrated course run instructions](README.md#integrated-course-run)

On 18 November, the four-analyst NVDA run ended `COMPLETED / BLOCKED` after its snapshot returned `OperationalError`. A fresh-cache repeat retained the snapshot and published Overweight. In a subsequent five-company batch, four reports received publication approval. AAPL retained a snapshot and exported 21 metric rows, but its recommendation was blocked for insufficient evidence. Its snapshot gives a direct FR-02 check: the upper Bollinger band (352.770608 USD) minus the closing price (348.245392 USD) was +4.525216 USD. A separate AAPL run published Overweight. [Online test results and cache controls](docs/live-acceptance.md)

### 6.4 CI and evidence limits

The integrated workflow executes the regression suite across Python versions and includes a non-UTC job. Separate jobs cover Ruff, a clean install and import, course schema and reference checks, permission parity and AI-use evidence. The artifact job runs the paired FR-03 comparison against a detached pinned upstream worktree. Hosted CI after the dependency and proxy corrections recorded a successful run for the integrated revision. That check applies to the recorded revision. The delivery head and its branch-protection status must be checked when the team requests final approval. [CI workflow](.github/workflows/ci.yml) · [Recorded hosted run](https://github.com/EverForests/TradingAgents_Pro/actions/runs/44241449315)

The course lists distinct blocking requirements for test approval, static analysis, schema validation, semantic evaluation, regression and the AI-use log. A passing workflow is evidence for the jobs it actually ran. The staged plan/test and human review records have to establish approval for the relevant changes. The fixed FR-03 comparison is a scoped behavioral check. Evidence of a general prompt/model semantic gate across the full project, and confirmation of final GitHub enforcement for protected paths, remain delivery review items. [Verification governance](docs/code-governance/verification-constraints.md) · [Technical debt register](docs/debt-register.md)

### 6.5 Reproduction and interpretation of receipts

The offline result can be reproduced using a checkout of the tested revision and a separate worktree of the pinned upstream reference. The README explains installation and the test entry points. For the recorded full run, the upstream worktree is passed as `FR03_BASELINE_ROOT`, the output directory for paired receipts is set separately, and the test process bypasses any local proxy for loopback. The terminal receipt includes the complete command, revision, dependency choices and JUnit result. The standalone paired run is also useful when a reviewer wants to inspect the comparison without waiting for the full suite. [Repository test instructions](README.md) · [Integration review](docs/review-memo.md)

The FR-03 paired comparison feeds controlled inputs into the pinned and improved implementations. The module handoff reports that five unsupported measurements in the baseline paired cases fell to zero and that valid neutral outcomes were preserved in all eleven associated cases. The 33 paired assertions also run in the integrated acceptance. Preserving the same stimulus and controlled model behavior makes the difference attributable to the tested logic for those cases. The counts describe the fixture set and should be reported with that denominator. The live diagnostic supplies a separate observation of zero-source behavior under actual provider conditions. [FR-03 handoff](docs/fr03.md) · [Derived comparison evidence](docs/fr03-evidence.json)

For live verification, compare the run identity, model profile, data window and request limit before interpreting counts. The normal first attempt and the diagnostic rerun had different limits, and the first receipt lacked the underlying failure subtype. Their attempt counts describe two runs with different outcomes. A meaningful comparison of model efficiency would need the same input and configuration, a comparable completed outcome, and measurements from the same boundary. The archived live reports support inspection of visible output and the presence or absence of a formal decision. Inspection of the empty starting memory and the resulting record count supplies evidence for the separate memory side effect. [Integrated course run instructions](README.md#integrated-course-run)

## 7. Process quality and optimization

### 7.1 Requirement volatility

The Git history records the initial requirement set, subsequent shared-contract refinements, bounded baseline evidence and the FR-02 source and sign clarification. The integrated acceptance evaluates the same five primary IDs. The main change during specification was clarification of measurement and interfaces, including evidence eligibility, the distinction between completed and approved, the identity and periods of operands, and the size representation for request preparation. The report therefore describes specific specification revisions and effects instead of deriving an unsupported percentage from document edit counts.

Clarification became easier to manage because the team preserved stable requirement identifiers. An acceptance case can change its fixture or expected source without creating a new product feature. When the change alters acceptance, the same requirement and contract must be updated alongside the fixture, checks and review record. For example, the sign clarification needed role-specific operands, a reverse-direction check and a trace entry. Describing the result only in the report would have left the tests and producer with different definitions.

There was also a distinction between refining a measurement and changing prior evidence. The NFR-01 re-baseline case count and test results were recorded in a new dated review entry, after the team found that stale counts referred to a different tree. The earlier figures remained attributable to the earlier revision. Applied consistently, this approach gives reviewers a requirement history and an evidence history that can be followed independently. [Requirements registry](docs/req/requirements.yaml) · [Review history](docs/review-memo.md) · [BUG-09](docs/bug-diary.md#bug-09---evidence-records-still-described-the-previous-baseline-2026-11-16)

### 7.2 Defect trends and investigation

| Stage | Observed examples | Process response |
| --- | --- | --- |
| Upstream diagnosis | Unsupported neutral sentiment on zero-source input, reported arithmetic discrepancies and unbounded request patterns. | Preserve observations, reproduce with controlled inputs and distinguish candidate defects from confirmed mechanisms. |
| Feature verification | False-green budget tests, ambiguous last-slot delivery assertions, malformed sentiment records and overly broad placeholder rules. | Inspect the assertion and failure route, use positive controls, add adverse cases, and preserve original evidence and scoped approvals. |
| Combined integration | Reminted run identity, sentiment state dropped by the subgraph, ungated sink assumptions and excess transport attempts. | Exercise real entry points with fixed sources and transport instrumentation, then review shared ownership and cross-feature outcomes. |
| CI and environment | Loopback proxy failures, duplicate case-insensitive CI environment keys and a fresh dependency changing the Bollinger-band calculation. | Reproduce under matched conditions, compare against the pinned reference where useful and record environment and dependency choices. |
| Live acceptance | Model transport failure with incomplete diagnostics, missing sentiment and a Yahoo response that provided no usable snapshot. | Separate HTTP status, workflow execution and publication. Verify deterministic outcomes with offline controls and retain the provider limitation. |

The observed defects changed in kind as the test scope expanded. Early problems were about representation and specification. Shared interfaces became more consequential when the five branches were assembled. Environment and dependency differences became visible only as tests moved from existing development environments to clean installs, hosted CI and live services. The diary has case-level evidence for these patterns. It does not contain a uniform sampling method from which to calculate a defect rate per week or per contributor. [Bug diary](docs/bug-diary.md) · [Combined-tree review](docs/review-memo.md)

### 7.3 Human oversight and follow-up

A useful human intervention was checking why a red baseline had unexpected passing tests. Two NFR-01 cases could go green because a constructor rejected an unexpected keyword before the intended behavior was reached. The observed pass would have been misinterpreted as budget evidence without inspecting the actual failure. Narrowing the assertions tied the tests to the intended reservation and dispatch behavior. The later public-dispatch race test also covered a gap in the primitive-level race scenario. These reviews improved the strength of the tests while keeping the original budget criterion.

Another intervention concerned reading and authority. When an agent did not have access to a relevant file, the team identified the missing exact permission and decided whether to grant it. When the verifier had not executed a test, the team attributed the result to the terminal receipt. When a component was ready but its runtime caller was still missing, the review retained conditional status. The main benefit was preserving the difference between an artifact existing, a component working under a test, and enforcement at the application boundary.

The CI callback timeout illustrates the danger of assigning a cause from timing alone. The same callback test reproduced the timeout on the baseline and the feature tree under matched conditions, and it passed after loopback traffic bypassed the proxy. The coordinated checks retained the regression and documented the environmental setting. The later Yahoo 429 investigation was a separate provider diagnosis. Neither observation establishes that all future live runs will have the same failure cause. [NFR-01 annotated process evidence](transcripts/nfr-01-request-budget.md) · [Review memo](docs/review-memo.md)

### 7.4 Co-evolution of deliverables

The requirement, architecture, implementation, acceptance and evidence layers answer separate questions. D1 specifies what is expected. D2 assigns authority, failure behavior and traceability. D3 and D9 constrain the agent workflow. D4 supplies executable criteria and review obligations. D5 provides the original interactions and marked interventions. D7 makes repeatable checks visible in CI. D8 exposes the application and its offline and online test entry points. This report describes the process and results using those artifacts as the detailed sources.

One example is the shared run identity. A conflict during integration caused the metric initialization to mint a second identity. C0 already required a shared run context. The integration repair preserved that context and updated the graph and fixtures to reflect the combined C1/C2 boundary. The tests then checked both metric registration and retained market evidence in the same flow. The review memo recorded the initial failure and the scoped correction, while the trace matrix linked to the integrated evidence. This is a stronger record than changing just the implementation and discarding the original counterexample.

Another example is the model-dispatch sequence. The D2 context and budget rules required preparation before reservation. C4 and C5 specified the exchanged records and failure order. Integration introduced a test that prepared irreducible input and measured the absence of both reservations and sends. The review applies this evidence to the documented sequence. Future changes to serialization, tool-schema handling or the budget counter would need corresponding updates to contracts, the affected fixtures and the revision-specific receipt. [Architecture blueprint](architecture-blueprint.md) · [Trace matrix](docs/architecture/trace-matrix.md) · [Review memo](docs/review-memo.md)

## 8. Limitations and delivery review

The integrated results support the five scoped requirements under the recorded deterministic verification. Live evidence supports the observed budget refusal, provider interaction, sentiment missingness, SEC metric recomputation and publication refusal. The evidence does not measure trading performance, the correctness of all model interpretations or provider availability over time. The verified metric table establishes the configured computations and the provenance we checked. The publication decision establishes legal rating and resolvable references under C1. Investment merit is a different claim.

The most direct remaining online gap is a successful publication with real, newly retrieved market evidence. Yahoo Finance is the current snapshot supplier for that path. Its connection failure and rate limiting were observed separately. A repeatable online positive check would require a substantive snapshot, accepted same-run references, an approved rating, an official report and the intended decision-memory entry. Availability of the snapshot alone would only establish that the upstream input is usable. The other gaps are live reproduction of the market-derived price example, observed live news-source coverage and live message-size instrumentation at the scoped provider boundary.

The team still needs to reconcile the delivery record. Some feature-level approval sources are private or incomplete, and the FR-03 intake records the absence of an individual student approval and final human verdict at that stage. The final integration reviewer should assess the delivery revision and record an actual dated verdict. Earlier module counts and the current executable results can support that review. A present-day review cannot establish an approval that was never recorded before implementation.

The submission also needs the completed student roster and contribution weights, member-authored reflections, and the annotated D5 transcripts assembled for the course. The public repository contains placeholders for those private records. The final package should link working reproductions, preserve the distinction between local and hosted evidence, and confirm the source/test layout and the course-required artifact structure. The application currently uses the inherited `tradingagents/` and `cli/` layout. The packaging check should resolve its relationship to the course `src/` requirement before delivery. [Architecture and packaging note](architecture-blueprint.md#integration-and-change-control) · [Transcript index](transcripts/README.md)

## 9. Team roster and relative contributions

The table records feature attribution from the intake and Git history. Repository names are provided to help match the entries to the corresponding students. Confirm the course-registered English names and student IDs in the private submission copy. The team must agree on one contribution measure and approve the underlying effort or story-point entries before publishing the relative weights.

| Scope | Repository attribution | Course-registered English name | Student ID | Confirmed effort or points | Relative contribution |
| --- | --- | --- | --- | ---: | ---: |
| FR-01, project coordination and integration | EverForests | Pending | Pending | Pending | Pending |
| FR-02 verified metrics | TangYunjian | Pending | Pending | Pending | Pending |
| FR-03 sentiment coverage | Wang Mingqian | Pending | Pending | Pending | Pending |
| NFR-01 request budget | JunKai Yan | Pending | Pending | Pending | Pending |
| NFR-02 bounded context | fjy | Pending | Pending | Pending | Pending |

Use the same measure for all five members and include review, coordination, integration and delivery work where the team has actual records. The relative contribution of a member equals their confirmed effort or points divided by the team mean. With five members, the mean of the five weights is 1.00 before rounding. Feature attribution gives the team a starting point for reconciliation. The weights must reflect the agreed and recorded work. [Feature intake](docs/review-memo.md#feature-pr-intake--2026-11-18)

## 10. Individual reflections

Each student supplies one English reflection of approximately 300–500 words, with their course-registered name and student ID. Replace each pending entry in the private submission copy. The prompts below identify recorded episodes that a student can discuss if they participated. The student should describe their own actions and link them to their annotated D5 evidence.

### 10.1 FR-01 and integration

**Student name and ID pending.** Reflection pending. Possible evidence includes separating candidate generation from publishing authority, testing the same rejected candidate through multiple consumers, or resolving shared run-state and transport conflicts during integration.

### 10.2 FR-02 verified metrics

**Student name and ID pending.** Reflection pending. Possible evidence includes locating the correct financial operands, freezing roles for signed calculations, or deciding how to treat an example with missing provider provenance.

### 10.3 FR-03 sentiment coverage

**Student name and ID pending.** Reflection pending. Possible evidence includes distinguishing an unavailable observation from a valid neutral one, reviewing contradictory provider receipts, or deciding what the controlled upstream comparison can establish.

### 10.4 NFR-01 request budget

**Student name and ID pending.** Reflection pending. Possible evidence includes investigating false-green cases, correcting delivery semantics, testing the last-slot race or separating a module verdict from an application-level claim.

### 10.5 NFR-02 bounded context

**Student name and ID pending.** Reflection pending. Possible evidence includes selecting mandatory blocks, validating the serialized message boundary, preserving tool pairs or checking the ordering between refusal and budget reservation.

## 11. Conclusion

The integrated application adds explicit controls to a working multi-agent baseline. Proposed arguments, verified values, coverage assessments, prepared requests and formal decisions have defined owners and observable failure states. The combined tests show that these owners can cooperate through normal entry points, including scenarios where missing data, exhausted budget or excessive context should change the outcome of the run.

The project also improved the team's verification process. A baseline revision made comparisons meaningful. Fixed adverse cases converted observations into reproducible defects. Exact file permissions and review records made agent authority inspectable. Integration tests caught issues that the feature suites could not observe, while separate online receipts showed where external services limited the evidence. Final delivery review can use these records to distinguish verified behavior, the remaining live coverage limits and administrative items still awaiting team completion.
