# Bug diary

Record one entry per significant defect, with symptom, reproduction, classification, confirmed root cause, fix, regression evidence, and the invariant gap exposed (or why none applies). Keep `unreproduced`, `root cause unknown` and `not fixed` explicit. Evidence sources and reproduction status are recorded per entry.

| ID and status | Symptom and classification | Reproduction to confirm | Root cause / fix / gap |
| --- | --- | --- | --- |
| BUG-01 — reported | NVDA revenue YoY, AAPL cost YoY/price difference, and MSFT capex/cash-flow ratio reportedly disagree with source calculations; numerical integrity | Freeze each original operand with source, period and unit; reproduce on the pinned baseline and compare recorded downstream/report values to independent calculations | Root cause unconfirmed; no fix recorded. FR-02 addresses the gap in verified arithmetic and record provenance; no separate invariant currently assigned. |
| BUG-02 — reproduced in controlled diagnostic | All three sentiment sources reportedly missing while the heading renders Neutral/5.0; missing-data semantics | Inject no valid source responses; inspect structured field, downstream input and title for disagreement | Representation limitation confirmed: UNKNOWN/null is unsupported by the baseline schema. FR-03 defines the correction; implementation and post-fix acceptance remain open. |

The large model inputs cited in D1 motivate NFR-02; reproduce them under fixed settings before treating them as a confirmed defect against the new cap. A publication or dispatch escape discovered during testing should be filed against INV-01 or INV-02 with the failed counterexample.

## Entry template

- **ID / date / status / reporter:**
- **Symptom and impact:**
- **Reproduction:** baseline or failing revision, fixture, steps, expected and actual result
- **Classification:** defect class, affected requirement and severity
- **Root cause and invariant gap:** evidence or unknown; invariant ID or rationale for N/A
- **Fix and regression evidence:** PR, failing-before/passing-after check and remaining limitations

## BUG-02 — Evidence record, 2026-11-15

The teammate-provided AAPL report (2026-11-03 through 2026-11-10; SHA256 `d425e9f0eb2b4c076b555e5f0ba95f48d7714a4684a036bae2c0f55b86c54450`) opens with Neutral/5.0 and low confidence while explicitly describing three unavailable sources. It describes Yahoo YFDataException, StockTwits history-window limits and Reddit fetch failure. These explanations are report contents, not independently inspected raw provider receipts. The five-stock summary repeats this heading observation; only the AAPL narrative has been supplied here. Numbered duplicate files have identical hashes and are not independent runs.

Pinned source inspection: `agents/schemas.py` defines six SentimentBand values without UNKNOWN, requires `overall_score: float` between 0 and 10, and renders it using numeric formatting. `analysts/sentiment_analyst.py` feeds the three prefetched text blocks to structured/free-text paths and stores report text. This establishes a representation limitation; it does not prove every live model must emit 5.0 or that real-world sentiment was neutral.

Status: artifact inspected and code mechanism identified. Independent controlled-node probe on 9fa1196 completed: 11 checks passed, zero external requests; null/UNKNOWN rejected, and an explicitly injected fake Neutral/5.0 flowed through the real node/renderer into a real bull-research prompt. A valid-data neutral synthetic control also passed. This demonstrates the missing guard, not a real model naturally choosing 5.0. An independent real-school sentiment-node diagnostic for AAPL/2026-11-10 also returned Neutral/5.0/Low with 0/3 valid sources. It added a human instruction limiting narrative to 160 English words, so it is a controlled diagnostic rather than an unchanged-configuration full-flow comparison. Report SHA256: `29ec0f5dbd5dffd055edf2c76850ed1d012f4eee065b65ba0b5b4d958123ca60`. FR-03/C3 specifies the correction. Fix status: Open; post-fix acceptance not executed.
