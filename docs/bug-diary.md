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

## BUG-03 — NFR-01 tests passed for the wrong reason, 2026-11-16

- **ID / date / status / reporter:** BUG-03 / 2026-11-16 / fixed / JunKai Yan (NFR-01 owner), found while reviewing the pre-change baseline.
- **Symptom and impact:** two acceptance tests were green against the pre-update draft although the C4 API did not exist. `test_t_nfr01_boundary_empty_run_id_rejected` and `test_t_nfr01_boundary_no_unmetered_mode_exists` accepted `(ValueError, TypeError)`, so the draft's `TypeError: unexpected keyword argument 'run_id'` satisfied them. Impact: the suite would have reported partial success for behaviour it never exercised, and the red baseline would have looked stronger than it was.
- **Reproduction:** run `pytest -q test/offline/test_request_budget.py` on the C4 test revision against the pre-update draft: `36 failed, 2 passed`. The two passes are these tests; the remaining failures are missing-contract-API errors.
- **Classification:** test-defect / false pass; NFR-01, INV-02; severity major for evidence integrity (not a product defect).
- **Root cause and invariant gap:** the expected-exception tuple conflated "invalid value rejected" with "constructor does not accept the argument at all". The requirement and C4 mandate rejection, not a specific exception class, so narrowing to `ValueError` (D-NFR01-01) is an owner-module implementation decision, not a requirement change.
- **Fix and regression evidence:** both assertions narrowed to `ValueError` by course-build under approval D-NFR01-01 (`ses_e1cc779c6ffeCuXn4SwJ3VszLK`). Pre-change baseline after the fix: `37 failed, 1 passed`; the only remaining pass is the static source guard, which is expected to be green on both sides. Post-implementation: 38 passed.

## BUG-04 — Last-slot race assertion contradicted C4 unknown-delivery accounting, 2026-11-16

- **ID / date / status / reporter:** BUG-04 / 2026-11-16 / fixed / JunKai Yan, found by human-run verification.
- **Symptom and impact:** `test_t_inv02_race_two_contenders_last_slot_once` failed with `assert 2 == 3` on `known_sends` while `charged_attempts == LIMIT` and `transport.send_count == LIMIT` were correct. Impact: a correct implementation would have been rejected, and a future maintainer could have "fixed" it by making `charge_attempt` claim delivery it cannot confirm.
- **Reproduction:** `pytest -q test/offline/test_request_budget.py` after implementation: `1 failed, 37 passed`, failing only in that test.
- **Classification:** test-defect / inconsistent expectation; NFR-01, INV-02; severity major for the affected case.
- **Root cause and invariant gap:** the race worker calls `try_reserve()` → `charge_attempt()` → `transport.send()` directly, bypassing `dispatch()`, which is the only path that receives delivery confirmation. C4 requires the snapshot to separate charged attempts, known sends and unknown-delivery attempts, so the winner's attempt must remain in `unknown_delivery`. The assertion demanded a confirmation the code path never produces.
- **Fix and regression evidence:** under D-NFR01-05 the test now asserts `charged_attempts == LIMIT`, `known_sends + unknown_delivery == LIMIT`, `unknown_delivery == 1`, `known_sends == LIMIT - 1`, and keeps `transport.send_count == LIMIT` as the actual INV-02 proof (`ses_e1cc528f0ffet72lN0NK1p1ohA`). After the fix: 38 passed. A mutation that removes the capacity bound still turns both race tests red, so the relaxed assertion did not weaken the enforcement check.

## BUG-05 — Reserved decision vocabulary in module prose, 2026-11-16

- **ID / date / status / reporter:** BUG-05 / 2026-11-16 / fixed / JunKai Yan, found during the documentation pass.
- **Symptom and impact:** the owner module described slot allocation as "holds one slot" and "a held slot". In this project `Hold` is a reserved decision term and C4 forbids implying a Hold rating on refusal, so the wording invited a vocabulary misreading by a reviewer or a future vocabulary gate, even though no behaviour was involved.
- **Reproduction:** vocabulary review of `tradingagents/llm_clients/request_budget.py` before the edit; the terms appeared in the module docstring and in `try_reserve`'s docstring.
- **Classification:** documentation/vocabulary ambiguity; NFR-01, C0; severity minor.
- **Root cause and invariant gap:** prose reused a decision word for a mechanical action. The gap is terminological, not behavioural; no invariant was violated.
- **Fix and regression evidence:** rephrased to "checks and reserves one slot" and "Reserve one slot" under D-NFR01-07 (`ses_e1cc4499fffeZbo0u61VgIjKcA`); 38 tests still pass and Ruff is clean.

## BUG-06 — Two lint defects in generated code and tests, 2026-11-16

- **ID / date / status / reporter:** BUG-06 / 2026-11-16 / fixed / JunKai Yan, found by human-run `ruff check`.
- **Symptom and impact:** `SIM105` in the test suite (try/except/pass instead of `contextlib.suppress`) and `UP035` in the module (`Callable` imported from `typing`). Impact: the repository's static-analysis gate would have blocked the change even though behaviour was correct.
- **Reproduction:** `ruff check tradingagents/llm_clients/request_budget.py test/offline/test_request_budget.py` → 2 errors.
- **Classification:** style/static-analysis defect; NFR-01; severity minor.
- **Root cause and invariant gap:** generated code used pre-3.10 idioms for exceptions and typing; the agent did not run lint (shell access is denied to the Build role by design).
- **Fix and regression evidence:** both fixed under D-NFR01-06 (`ses_e1cc528f0ffet72lN0NK1p1ohA`); `ruff check .` clean repo-wide and 38 tests still pass.

## BUG-07 - Required planning documents were not readable by the planning role, 2026-11-16

- **ID / date / status / reporter:** BUG-07 / 2026-11-16 / fixed in baseline `1a54b9c` / reported by a teammate, confirmed independently by JunKai Yan.
- **Symptom and impact:** `Prompt.md` line 37 requires reading the documentation index and open review items before planning, but `.opencode/permissions.jsonc` allowed read on `docs/architecture/*`, `docs/req/*` and `docs/code-governance/*` only. `course-plan` could read `AGENTS.md` and `Prompt.md` and was refused `docs/README.md` and `docs/review-memo.md`. Impact: every plan produced under the old allowlist either stopped or was planned from material the role could not read, which weakens the Gate 1 evidence for all five requirements.
- **Reproduction:** run `course-plan` on baseline `486a9a5` with a task header naming those two paths; both reads return `Permission denied: read`. Under `3d5ce62` the same request succeeds for `docs/README.md`, `docs/review-memo.md` and `docs/req/product.yaml`.
- **Classification:** tooling/configuration defect; NFR-01 and all requirements using Gate 1; severity major for evidence integrity.
- **Root cause and invariant gap:** the allowlist enumerated documentation subdirectories instead of the files the workflow names, so a new top-level document in `docs/` was silently unreadable. The permission model requires a missing read to be reported and fixed by a human, which is what happened; the earlier workaround of pasting content into the session is not a valid substitute and is not repeated.
- **Fix and regression evidence:** `1a54b9c` adds the three read entries to both `.opencode/opencode.jsonc` and `.opencode/permissions.jsonc`; the admin file and the effective file stay identical. Verified by the round-2 plan session `ses_e1cb0bce4ffeSMiYzgvWzPty3y`, which read twelve required documents with no denial. An interim local patch adding the same two entries was reverted once `1a54b9c` was found to contain them, so no duplicate configuration change is claimed.

## BUG-08 - Race coverage did not reach the dispatch boundary, 2026-11-16

- **ID / date / status / reporter:** BUG-08 / 2026-11-16 / fixed / found by `course-plan` in the round-2 plan, confirmed by Gate 4.
- **Symptom and impact:** all three T-INV02-RACE cases either used `try_reserve`/`charge_attempt`/`send` directly or raced eight threads through `dispatch` without contending for the last slot. A regression that broke delivery confirmation or double-charged on the `dispatch` path under contention would not have been caught. Impact: the suite could stay green while the most likely integration error went unnoticed.
- **Reproduction:** remove `budget._mark_delivered(ticket)` from `dispatch` before the fix and run the suite: 39-case equivalent set fails only in tests that assert `known_sends` directly, none of them a two-thread last-slot race through `dispatch`. After the fix the same mutation fails five cases including the new one.
- **Classification:** test-defect / non-discriminating coverage; NFR-01, INV-02; severity major for the race case, no product defect.
- **Root cause and invariant gap:** the original race design tested the primitive layer because it was easier to synchronise, and the dispatch-level case used eight threads that exhausted the budget without two contenders hitting the last slot. The frozen case ID was therefore covered only at the layer below the contract boundary.
- **Fix and regression evidence:** one test appended under D-NFR01-09 (`ses_e1caf1566ffeefvZW8dDBgx8mJ`), lines 741-806, no existing line changed. Evidence: 39 passed; mutation M3p turns it red with `known_sends=0` while `charged_attempts == LIMIT`, and the pre-fix suite returned 38 passed. Recorded as a coverage addition whose discrimination is proven by mutation, not as a fixed product defect.

## BUG-09 - Evidence records still described the previous baseline, 2026-11-16

- **ID / date / status / reporter:** BUG-09 / 2026-11-16 / fixed / found by Gate 4 `ses_e1cab4f89ffed8ePmZwWo5Ljy0` during record-integrity review.
- **Symptom and impact:** after the branch moved to `3d5ce62`, the NFR-01 evidence block in the trace matrix still said base `486a9a5`, 253 lines and 38 tests, and PR-NFR01-001 still quoted 38 passed, 1450 regression and the old 8/3/1 mutation counts. Impact: a reviewer comparing the record with the tree would find numbers that no longer matched, and the discrepancy would read as either stale evidence or an inflated claim.
- **Reproduction:** compare the trace-matrix NFR-01 block and PR-NFR01-001 against `git diff 486a9a5 3d5ce62` and a 39-case suite; the file sizes and counts disagree.
- **Classification:** documentation/record defect; NFR-01; severity major for evidence integrity, no behavioural impact.
- **Root cause and invariant gap:** the evidence block was written once for one revision and then treated as a living section. The review procedure requires a new dated entry per reviewed revision; editing the old entry in place would instead have implied the old run measured the current tree.
- **Fix and regression evidence:** the old heading is marked superseded in place, a new re-verification block is added for `3d5ce62`, and PR-NFR01-002 is appended for the new revision while PR-NFR01-001 is left intact. Session IDs from both rounds are listed explicitly because Gate 4 flagged the two sets as unreconciled.
