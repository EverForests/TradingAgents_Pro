# Bug diary

Record one entry per significant defect, with symptom, reproduction, classification, confirmed root cause, fix, regression evidence, and the invariant gap exposed (or why none applies). Keep `unreproduced`, `root cause unknown` and `not fixed` explicit. Evidence sources and reproduction status are recorded per entry.

| ID and status | Symptom and classification | Reproduction to confirm | Root cause / fix / gap |
| --- | --- | --- | --- |
| BUG-01 — reported | NVDA revenue YoY, AAPL Cost of Revenue YoY/upper-band-minus-close gap, and MSFT capex/cash-flow ratio reportedly disagree with source calculations; numerical integrity | Freeze each original operand with source, period and unit; reproduce on the pinned baseline and compare recorded downstream/report values to independent calculations | Root cause unconfirmed; no fix recorded. FR-02 addresses the gap in verified arithmetic and record provenance; no separate invariant currently assigned. |
| BUG-02 — module fix verified; integration pending | All three sentiment sources reportedly missing while the heading renders Neutral/5.0; missing-data semantics | Inject no valid source responses; inspect structured field, downstream input and title for disagreement | Representation limitation confirmed: UNKNOWN/null is unsupported by the baseline schema. FR-03 module fix is verified at b2816ec; formal human and joint acceptance remain open. See the dated update below. |

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

Status: artifact inspected and code mechanism identified. Independent controlled-node probe on 9fa1196 completed: 11 checks passed, zero external requests; null/UNKNOWN rejected, and an explicitly injected fake Neutral/5.0 flowed through the real node/renderer into a real bull-research prompt. A valid-data neutral synthetic control also passed. This demonstrates the missing guard, not a real model naturally choosing 5.0. An independent real-school sentiment-node diagnostic for AAPL/2026-11-10 also returned Neutral/5.0/Low with 0/3 valid sources. It added a human instruction limiting narrative to 160 English words, so it is a controlled diagnostic rather than an unchanged-configuration full-flow comparison. Report SHA256: `29ec0f5dbd5dffd055edf2c76850ed1d012f4eee065b65ba0b5b4d958123ca60`. FR-03/C3 specifies the correction. Historical status at 2026-11-15: fix open. The subsequent dated update records module verification without rewriting the original evidence.

## BUG-01 measurement clarification

[SRC-06](review-memo.md#source-register) defines the AAPL annual field as `Cost of Revenue` and the positive gap as Bollinger upper band minus close. [D4](code-governance/verification-constraints.md#fr-02-aapl-acceptance-examples) records operand roles, fiscal labels, units, signed expectations and evidence status. This clarifies the planned reproductions; the reported model discrepancy remains unconfirmed and no application fix is recorded.

## FR03 fix evidence — 2026-11-17

| Item | Symptom, reproduction and root cause | Fix and actual regression | Status / invariant boundary |
|---|---|---|---|
| BUG-02 | Original 9fa1196 cannot represent UNKNOWN/null and calls the model on no evidence. Original real diagnostic and explicit fake-node probe are distinct evidence layers. | Deterministic source coverage, zero-source skip and canonical assessment. Final b2816ec paired: 5 unsupported measurements to 0; valid Neutral 11/11 preserved; 33 assertions passed. | Module fix verified; formal human and C1/C4 acceptance pending. Does not prove investment correctness. |
| FR03-B01 | Blank/error body with valid-looking item metadata counted as evidence; malformed containers/counts/refs/blank identities could inflate coverage or crash. First 40 new cases on 0aebc95: 27 failures. | b4c057c validates contradictory bodies, shapes, exact identity and count/ref agreement, preserving valid mixed inputs. | Verified by final 47 boundary controls. Missingness must not create authoritative observations. |
| FR03-B02 | A score of ±10**400 raised OverflowError before range validation in the plain-mapping path; two pre-fix cases failed. | Bounds checked before float conversion; UNKNOWN/null/SCORE_INVALID retains actual coverage. | Both negative cases pass. No new publication invariant is claimed. |
| FR03-B03 | Broad No-found placeholder detection rejected substantive headlines; raw/canonical ticker equivalents were accepted by the node but rejected by attribution checks. Five positive cases failed on b4c057c. | b2816ec restricts plain empty markers to the vendor sentence and uses existing pure canonical symbols only for source/item attribution. Exact run identity stays unchanged. | Five cases pass; wrong ticker/empty/error rejection remains covered. |

See [FR-03](fr03.md), [derived evidence](fr03-evidence.json) and FR03-REVIEW-006. Original raw records remain private and unchanged.
