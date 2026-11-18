# Live acceptance: Yahoo market evidence

The integrated application at `ab84ed1` completed an online NVDA analysis on 18 November 2026, but **did not publish an official recommendation**. The analysis date was 10 November. The run ended `COMPLETED / BLOCKED` with reason `INSUFFICIENT_EVIDENCE`. The saved Markdown and HTML are diagnostic outputs. This run does not satisfy the `COMPLETED / APPROVED` acceptance case.

| Check | Observed result | What it establishes |
| --- | --- | --- |
| Coordinator's provider preflight | After an initial connection error, both Yahoo chart endpoints returned HTTP 429. The snapshot exhausted its retry policy and returned `DATA_UNAVAILABLE`; no evidence records were retained and no model calls were made. | Yahoo rate limiting was observed in that session. The cause of the provider's decision is unknown. |
| Integrated four-analyst run, NVDA | The market analyst requested history and a snapshot in the same turn. History returned 252 rows; the snapshot returned `DATA_UNAVAILABLE` with `OperationalError`. No HTTP 429 was recorded. | The run log retained the exception class but not the underlying message. A cache lock is consistent with it, not proven for this run. |
| Integrated live tool checks, fresh caches | NVDA (two rounds), AAPL and MSFT (one each). Each round called both market tools serially in one process and concurrently in another. All 8 serial calls and 7 of 8 concurrent calls succeeded. | The MSFT snapshot failed before its first HTTP request. Its stack showed `database is locked` while Peewee applied SQLite settings for the yfinance timezone cache. Across all eight processes, 0 of 42 observed HTTP responses were 429. These were tool checks, not full report runs. |

## Did the integration introduce the lock?

The same two tools already exist on upstream `9fa1196`. With `yfinance 1.8.0` and `peewee 4.5.3`, the unmodified upstream ToolNode received both calls in one model turn and hit the same lock in **4 of 100** fresh-cache trials. A second upstream check synchronized the two threads at startup: 9 of 100 concurrent trials locked, compared with 0 of 100 serial trials and 0 of 100 concurrent trials after cache initialization. These controls exercised the real SQLite path offline and stopped before fetching market data; they do not measure a production failure rate.

The lock therefore does not require a student feature or the merge. This comparison establishes baseline behavior with the tested dependencies; it does not reconstruct the original demo environment. Track the provider's 429 separately. For a future 429 retain the endpoint, timestamp, status and `Retry-After` if supplied. For a cache failure retain the underlying exception and cache initialization stack. A fresh live run with sufficient evidence and an approved publication is still needed for positive acceptance.
