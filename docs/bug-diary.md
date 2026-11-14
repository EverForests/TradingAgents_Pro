# Bug diary

Record one entry per significant defect, with symptom, reproduction, classification, confirmed root cause, fix, regression evidence, and the invariant gap exposed (or why none applies). Keep `unreproduced`, `root cause unknown` and `not fixed` explicit. The intake below is based on team observations, not runs performed for this document.

| ID and status | Symptom and classification | Reproduction to confirm | Root cause / fix / gap |
| --- | --- | --- | --- |
| BUG-01 — reported | NVDA revenue YoY, AAPL cost YoY/price difference, and MSFT capex/cash-flow ratio reportedly disagree with source calculations; numerical integrity | Freeze each original operand with source, period and unit; reproduce on the pinned baseline and compare recorded downstream/report values to independent calculations | Root cause unconfirmed; no fix recorded. FR-02 addresses the gap in verified arithmetic and record provenance; no separate invariant currently assigned. |
| BUG-02 — reported | All three sentiment sources reportedly missing while the heading renders Neutral/5.0; missing-data semantics | Inject no valid source responses; inspect structured field, downstream input and title for disagreement | Root cause unconfirmed; no fix recorded. FR-03 addresses distinction between missing and measured neutral; no separate invariant currently assigned. |

The large model inputs cited in D1 motivate NFR-02; reproduce them under fixed settings before treating them as a confirmed defect against the new cap. A publication or dispatch escape discovered during testing should be filed against INV-01 or INV-02 with the failed counterexample.

## Entry template

- **ID / date / status / reporter:**
- **Symptom and impact:**
- **Reproduction:** baseline or failing revision, fixture, steps, expected and actual result
- **Classification:** defect class, affected requirement and severity
- **Root cause and invariant gap:** evidence or unknown; invariant ID or rationale for N/A
- **Fix and regression evidence:** PR, failing-before/passing-after check and remaining limitations
