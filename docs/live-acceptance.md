# Live acceptance: multi-company publication and Yahoo market evidence

The five-company CLI rerun on 19 November 2026 approved **5 of 5** on application revision `df8a9d6`, using analysis date 10 November. [Settings, results and evidence limits](#five-company-cli-rerun-on-19-november-2026) are recorded below. The earlier 18 November batch approved **4 of 5**; a separate AAPL diagnostic rerun supplied the fifth company approval. The historical blocked runs and coordinator API checks remain separate records.

## Initial NVDA run: blocked publication

The integrated application at `ab84ed1` finished the online NVDA analysis as `COMPLETED / BLOCKED`, with reason `INSUFFICIENT_EVIDENCE`. Its Markdown and HTML are diagnostic outputs; the official recommendation was withheld.

| Check | Observed result |
| --- | --- |
| Coordinator's provider preflight | After an initial connection error, both Yahoo chart endpoints returned HTTP 429. The snapshot exhausted its retries and returned `DATA_UNAVAILABLE`. It retained no evidence records and made no model calls. |
| Integrated four-analyst NVDA run | The market analyst requested history and a snapshot in one turn. History returned 252 rows; the snapshot returned `DATA_UNAVAILABLE` with `OperationalError`. The log recorded no HTTP 429. |
| Integrated live tool checks with fresh caches | NVDA had two rounds; AAPL and MSFT had one each. Each round called both market tools serially in one process and concurrently in another. All 8 serial calls and 7 of 8 concurrent calls succeeded. The MSFT snapshot failed before its first HTTP request: its stack showed `database is locked` while Peewee applied SQLite settings to the yfinance timezone cache. Across eight processes, 0 of 42 observed HTTP responses were 429. |

## Upstream cache-lock controls

The same two tools exist on unmodified upstream `9fa1196`. With `yfinance 1.8.0` and `peewee 4.5.3`, its ToolNode received both calls in one model turn and hit the lock in **4 of 100** fresh-cache trials. A second check synchronized both threads at startup:

| Upstream condition | Trials with a lock |
| --- | ---: |
| Concurrent calls, fresh cache | 9 / 100 |
| Serial calls, fresh cache | 0 / 100 |
| Concurrent calls, initialized cache | 0 / 100 |

These offline controls exercised the real SQLite path and stopped before fetching market data. They reproduce the initialization lock on unchanged upstream code with the tested dependencies.

For future failures, retain the endpoint, timestamp, HTTP status and `Retry-After` for a 429, and the underlying exception and cache initialization stack for a cache error.

## Single NVDA repeat run: approved publication

At 22:38:44 on 18 November 2026 (Asia/Shanghai), the four-analyst CLI at `7027e81` finished with exit 0 using fresh caches. Changes since `ab84ed1` were documentation only. The saved state recorded `execution_status=COMPLETED`, `publication_status=APPROVED`, no block reason, and `final_rating=Overweight`.

The run retained the market snapshot, included SEC data in the fundamentals report, and displayed the official rating in the consolidated report. It recorded no Yahoo 429 or cache-lock error. A Reddit RSS request returned 429.

## Five-company batch: four approved, one blocked

The batch summary timestamped `2026-11-18T15:08:40.934829+00:00` records exit 0 and `execution_status=COMPLETED` for all five runs:

| Ticker | Publication | Official rating | Exported metrics | Retained market snapshots |
| --- | --- | --- | ---: | ---: |
| NVDA | APPROVED | Underweight | 27 | 1 |
| AAPL | BLOCKED (`INSUFFICIENT_EVIDENCE`) | None | 21 | 1 |
| MSFT | APPROVED | Overweight | 58 | 1 |
| GOOGL | APPROVED | Underweight | 15 | 1 |
| AMZN | APPROVED | Overweight | 47 | 1 |

NVDA received **Underweight** in this batch and **Overweight** in the earlier single rerun. Both executions remain in the record. AAPL completed with a retained market snapshot and a blocked publication.

Each batch run had one SEC cache entry, zero retained raw SEC responses, and zero logged model-provider errors. This error count covers model-provider logs. Exported metric counts come from saved artifacts, without an in-memory registry check; the final-state serializer omits that registry.

## AAPL diagnostic rerun: approved publication

The separate AAPL diagnostic rerun finished on 18 November with exit 0 after **208.4 seconds**. Its observer recorded no observer errors, no source changes during execution, and 19 model HTTP responses, all 200.

The publication gate and downstream `publish`, `record_decision`, `_log_state` and `save_reports` events recorded `COMPLETED / APPROVED`, no block reason, and `final_rating=Overweight`. The gate resolved this chain:

```text
arg:bear:8c983d06bed24c4fbb7ce63dbad47b8c:2
  -> ev:8c983d06bed24c4fbb7ce63dbad47b8c:market_snapshot:call_01_62EkLR4D1B44g5nehcra8927
  -> market_snapshot (yahoo)
```

The resolver returned the referenced content on all three observed calls. The Bull Analyst submitted another evidence ID that was absent from the admissible registry, so its argument was rejected. The Bear Analyst's snapshot-backed argument was accepted, the Portfolio Manager cited it, and the gate approved publication. The observer's `metric_count` reads a legacy key and provides no verified metric total.

## Evidence and interpretation

The batch table comes from the local receipt `saved_results_summary.md`; AAPL rerun details come from the local gate trace summary `diagnostic_summary.json`. These saved artifacts are outside the committed test fixtures. This documentation update used saved artifacts and made no online requests.

Rating stability and resolution of intermittent Yahoo or cache failures remain unverified. The offline controls cover the tested dependencies; production failure rates and the original demo environment were outside their scope. Yahoo's reason for returning 429 is unknown. The first NVDA run retained only the `OperationalError` class, leaving its cause unresolved. The original AAPL artifacts omit the candidate references and admissible registry state needed to explain its block; the later rerun records a separate execution.

## Coordinator reproduction — 19 November 2026

A new local reproduction used the working tree based on `77938d0` with the FR-01 reference-selection repair. It analyzed AAPL as of 10 November through the Python graph API with market, social, news and fundamentals analysts and `CS5351/DeepSeek-V4-Flash` on both tiers. The application patch SHA-256 was `c3e608283151c87818af77163a9095d969d06c69b02ffe3b7e865094ba4c941b`. This differs from the earlier teammate CLI revision. The application source remained stable during the checks.

Yahoo preflight succeeded and supplied a verified close window from 30 September through 10 November. Each run used empty decision memory and a new result directory. Subsequent attempts copied the real Yahoo cache downloaded by the first attempt. None used the synthetic source from the earlier component replay.

| Attempt | Scheduling / route | Actual configured request limit | Observed model HTTP attempts | Result |
| --- | --- | ---: | ---: | --- |
| Default | Four-analyst default scheduling | 40 | 4, including one HTTP 200 and three ConnectError outcomes | FAILED / BLOCKED / RUN_NOT_COMPLETE |
| Retry | Default scheduling, previously fetched Yahoo cache | 40 | 3 ConnectError outcomes, with local address assignment and connection reset errors | FAILED / BLOCKED / RUN_NOT_COMPLETE |
| Serial diagnostic | All four analysts, graph max_concurrency=1 | 40 | 12, with eleven HTTP 200 and one local address assignment failure | FAILED / BLOCKED / RUN_NOT_COMPLETE |
| Explicit proxy diagnostic | Default scheduling, model transport explicitly uses the configured local system proxy | 21 | 5, with three HTTP 200 and two TLS unexpected-EOF errors | FAILED / BLOCKED / RUN_NOT_COMPLETE |

The serial diagnostic initially mislabeled its request ceiling as 33 in the receipt, while the actual runner configuration remained 40. Its twelve attempts stayed below both values. The retained original receipt and corrected receipt document the labeling correction. Across the four receipts, 24 model HTTP attempts were observed.

In the serial diagnostic, the Bull returned E1. The adapter resolved it to the retained market snapshot, and argument validation accepted it. The Bear supplied the full snapshot ID and was also accepted. The run subsequently failed before it could publish a final decision. Every attempt returned the API sentinel REVIEW, withheld an official rating and decision file, and left decision memory empty.

The system HTTPS proxy was enabled on local port 11888. A model metadata request returned HTTP 200. The metered model client owns its HTTP transport, so successful metadata access alone does not establish that ordinary model requests use the same proxy route. The explicit-proxy diagnostic retained the existing budget wrapper and changed only the inner HTTP transport in the private test harness. It still encountered TLS errors. The serial and proxy diagnostics therefore do not establish a fix for the connection problem.

These checks verified fresh Yahoo availability and short-reference acceptance with real market evidence on this machine. They did not reproduce the teammate's COMPLETED / APPROVED outcome. No application code, proxy settings or SDK retry policy was changed during this reproduction. Private receipts, diagnostic reports and runners are retained in the local course archive `FR01-reference-reliability-2026-11-19`, under the `live-reproduction-*` directories.

## Published reference adapter verification — 19 November 2026

The coordinator pushed the reference adapter as `df8a9d6419dfa0aab2f4d8986d0a44060354cdb9` and verified that exact clean application revision through the Python API. Its push and PR CI completed successfully. Each run used AAPL, analysis date 2026-11-10, all four analysts, the real school-hosted DeepSeek model, a request limit of 40, empty decision memory and an independent results directory.

| Run | Market-data condition | Model HTTP attempts | Execution / publication | Official outputs |
| --- | --- | ---: | --- | --- |
| Fresh-cache attempt | Yahoo preflight and later tools were rate limited | 21, all HTTP 200 | COMPLETED / BLOCKED / INSUFFICIENT_EVIDENCE | No official rating, decision file or new memory entry |
| Real-data cache replay | Reused real Yahoo AAPL history downloaded earlier on 19 November; verified window ended on 2026-11-10 | 18, all HTTP 200 | COMPLETED / APPROVED; Overweight | API rating, Markdown/HTML reports, official decision file and one new memory entry verified |

Both researchers in the approved run selected E1. The program resolved it to the full current-run market snapshot ID and accepted both arguments. The manager selected A1 and A2. The publication result carried canonical argument and evidence IDs, with two resolvable links to the snapshot. Verification re-read the retained source, checked that the decision and memory contained the approved rating, and confirmed that the Markdown and HTML reports existed. The run took 198.56 seconds.

The success uses real cached market data and live model requests. It establishes the full graph API publication path with the revised prompts and adapters. Fresh uncached Yahoo retrieval and a new live CLI rendering check remain unverified by this run. Missing news and social inputs remained explicit. The private archive `FR01-df8a9d6-live-2026-11-19` contains receipts, reports, source and decision hashes, the runner and CI metadata. These runs used no synthetic market fixture or replacement provider response. [Push CI](https://github.com/EverForests/TradingAgents_Pro/actions/runs/44467792904) · [PR CI](https://github.com/EverForests/TradingAgents_Pro/actions/runs/44467801241)

## Five-company CLI rerun on 19 November 2026

One sequential batch reran NVDA, AAPL, MSFT, GOOGL and AMZN through the real CLI at `df8a9d6419dfa0aab2f4d8986d0a44060354cdb9`. Each company had one attempt, fresh result and cache directories, and empty decision memory. The saved verification matched 106 application files to that revision before and after execution. All five runs exited 0 and recorded `COMPLETED / APPROVED`, with no publication block reason. Total elapsed time was 1,085.90 seconds.

| Setting | Recorded value |
| --- | --- |
| Analysis date | `2026-11-10` |
| CLI arguments | `--ticker <ticker> --date 2026-11-10 --analysts market,social,news,fundamentals --save --no-show` |
| Provider and endpoint | `openai_compatible`; `https://llm.cs.cityu.edu.hk/v1` |
| Quick and deep models | `CS5351/DeepSeek-V4-Flash` on both tiers |
| Request budget | Enabled; 40 per company, 200 across the five configured limits |
| Debate / risk rounds | 1 / 1 |
| Checkpoints / output | Disabled / English |
| Data vendors | Yahoo for market, indicators and news; `sec_edgar,yfinance` for fundamentals; FRED for macro; Polymarket for prediction markets |

The limits above are configuration values. This batch retained no inner-transport model-attempt count, so 200 is the sum of the configured ceilings. Zero logged model-provider errors is a separate observation.

| Ticker | Execution / publication | Official rating | Exported metrics | Market snapshots | Elapsed seconds |
| --- | --- | --- | ---: | ---: | ---: |
| NVDA | COMPLETED / APPROVED | Underweight | 17 | 1 | 215.46 |
| AAPL | COMPLETED / APPROVED | Hold | 43 | 1 | 195.89 |
| MSFT | COMPLETED / APPROVED | Overweight | 58 | 1 | 200.83 |
| GOOGL | COMPLETED / APPROVED | Hold | 15 | 1 | 249.09 |
| AMZN | COMPLETED / APPROVED | Overweight | 68 | 1 | 224.63 |

Each retained snapshot names 2026-11-10 as both the requested analysis date and latest trading row. The saved report headers agree with the official ratings in the table. Exported metric counts describe saved rows; the serializer omits the in-memory registry, so this review did not re-verify those rows against it. Each company retained one SEC company-facts cache and logged statement-tool calls, with zero retained raw SEC statement-response bodies. These artifacts support SEC use; generated fundamentals prose supplies no additional raw receipt.

Raw Data/Tool/System and terminal logs record continuing input limits: Yahoo news fetch failures (`YFDataException`) and unsupported historical global-news windows, missing FRED configuration, and withheld Polymarket odds because historical vintages were unavailable. Every company logged a Reddit RSS HTTP 404 and free-text fallback for both Research Manager and Trader after structured output returned no parsed result. These are observed provider and parsing outcomes. The saved scan found zero model-provider error logs and no explicit Yahoo HTTP 429, SQLite-lock or reference-rejection diagnostic in this batch. Missing rejection logs do not establish that every submitted candidate was accepted. Diagnostic counts in the receipts count log occurrences and can repeat one event across logs.

The saved comparison with the 18 November five-company batch shows:

| Ticker | Earlier publication / official rating | Rerun publication / official rating | Earlier / rerun metric rows |
| --- | --- | --- | ---: |
| NVDA | APPROVED / Underweight | APPROVED / Underweight | 27 / 17 |
| AAPL | BLOCKED / None | APPROVED / Hold | 21 / 43 |
| MSFT | APPROVED / Overweight | APPROVED / Overweight | 58 / 58 |
| GOOGL | APPROVED / Underweight | APPROVED / Hold | 15 / 15 |
| AMZN | APPROVED / Overweight | APPROVED / Overweight | 47 / 68 |

All five market snapshot cores matched: OHLCV, indicators, recent close rows and quote receipts. Exported metric value/unit sets differed for all five companies, including MSFT and GOOGL, whose row counts stayed equal. AAPL changed from blocked to approved; GOOGL's official rating changed to Hold. These are separate model executions on different application revisions, with unchanged market snapshot cores and differing generated outputs. The comparison establishes neither rating stability nor a causal effect of the reference adapter. It also leaves the cause of the earlier AAPL block unresolved.

Evidence is retained outside the public repository in the course archive `project-new/个人记录/在线复跑_20261119_df8a9d6`. Resolve the following locators from that archive root: `batch_manifest.json` and `<ticker>/execution_settings.json` for settings; `execution_results.json` for exits and timing; `source_verification.json` and `final_validation.json` for source hashes and artifact inventory; `saved_results_summary.json` for states, report paths, snapshot fields and raw diagnostic line locators; and `saved_run_comparison.json` for the earlier/rerun comparison. Per-company source logs are `<ticker>/terminal.log` and `<ticker>/results/<ticker>/2026-11-10/message_tool.log`; final states are `<ticker>/results/<ticker>/TradingAgentsStrategy_logs/full_states_log_2026-11-10.json`. This documentation review read saved artifacts and made no online requests. The executed CLI path used `--no-show`; interactive terminal rendering was outside this check.
