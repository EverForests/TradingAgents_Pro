# Live acceptance: multi-company publication and Yahoo market evidence

Saved artifacts from 18 November 2026 show approved publications for **five unique companies across separate attempts**, all using analysis date 10 November. The five-company batch approved **4 of 5**; a later AAPL diagnostic rerun supplied the fifth approval. The record also includes blocked NVDA and AAPL runs.

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
