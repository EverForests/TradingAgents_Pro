# NFR-01 annotated session summary (owner: NFR-01)

This file is a sanitized working summary for the NFR-01 owner. It is not a raw transcript: raw OpenCode session data stays in the private archive (`~/cs5351/sessions-nfr01/`) and must not be pushed to the public repository. At submission time, merge the relevant sections into the owner's `member-*.md` transcript and rename it `<student-id>-<name>.md` as D5 requires.

- Requirement: NFR-01 (§2.3), invariant INV-02, contracts C0/C4, ADR-001.
- Base revision: `486a9a5d74433aedd3c858c483a8d77bf0f7b897` (merge of PR #5).
- Branch: `feat/nfr-01-request-budget` (not pushed at the time of writing).
- Tool: OpenCode 2.3.0, agent roles `course-plan` (read-only), `course-build`, `course-verify` (read-only), model `cityucs/CS5351/DeepSeek-V4-Flash`.
- Human: JunKai Yan (owner), who ran every verification command and issued decisions D-NFR01-01..08.

## Session sequence

| # | Session | Role | What the human asked | What the agent produced |
| --- | --- | --- | --- | --- |
| 1 | `ses_e1cce6943ffeM6m8a640UGrQql` | course-plan | Five-section Gate 1 plan for NFR-01 on the new baseline, treating the pre-update draft as unapproved | Plan with 8 open questions, ended with WAITING FOR PLAN AND TEST APPROVAL |
| 2 | `ses_e1cccc9f2ffeeYPMCG5yAtO7Ri` | course-build | Tests first, six frozen case IDs, inline fixtures, no production code | 38 tests in `test/offline/test_request_budget.py` |
| 3 | `ses_e1cc779c6ffeCuXn4SwJ3VszLK` | course-build | D-NFR01-01: remove a false pass by narrowing an exception tuple | Two assertions narrowed to `ValueError` |
| 4 | `ses_e1cc653a7ffehmuDFjT84hozEK` | course-build | Implement C4 v1.0 in one owner module | 253-line module with atomic reservation, dispatch, typed failures |
| 5 | `ses_e1cc528f0ffet72lN0NK1p1ohA` | course-build | D-NFR01-05/06: fix the race assertion and two lint defects | Corrected snapshot assertions, `contextlib.suppress`, `collections.abc.Callable` |
| 6 | `ses_e1cc4499fffeZbo0u61VgIjKcA` | course-build | D-NFR01-07: remove reserved decision vocabulary from prose | Two docstrings rephrased |
| 7 | `ses_e1cc3cde9ffev4PHpzLJ9n611D` | course-verify | Read-only compliance review of the change set | "Conditionally compliant", 12 findings, six refused overclaims |
| 8 | `ses_e1cc29b21ffen2sr32O58Fh5Aj` | course-build | D-NFR01-08: add the ADR citation required by structural constraints | Docstring header line updated |

## Human decisions recorded

- D-NFR01-01 invalid constructor arguments raise `ValueError` (removes a false pass; not a requirement change).
- D-NFR01-02 resume disabled: no reset/restore/refill API; a new run uses a new `run_id`.
- D-NFR01-03 provider failure raises `ProviderFailure` with the original exception as `__cause__`; the slot stays charged as an unknown-delivery attempt.
- D-NFR01-04 `try_reserve()` returns `None`; `dispatch()` converts it to `BudgetExhausted`.
- D-NFR01-05 the last-slot race test asserts `known_sends == limit - 1` and `unknown_delivery == 1`, because the worker uses the primitives and bypasses `dispatch()`'s delivery confirmation.
- D-NFR01-06 lint-only fixes; D-NFR01-07 vocabulary wording; D-NFR01-08 ADR citation.

## Verification the human ran

- Red baseline: `pytest -q test/offline/test_request_budget.py` → 37 failed, 1 passed (the pass is the static source guard).
- Green: `pytest -q test/offline` → 38 passed.
- Regression: `pytest -q tests test/offline` → 1450 passed, 1 skipped (`langchain_aws` absent), 1 deselected.
- Static analysis: `ruff check .` clean; `git diff --check` clean; 38 cases collected.
- Mutations (external plugin, deleted afterwards): capacity bound removed → 8 failed including both race tests; `cancel_before_send` neutralised → 3 failed; delivery confirmation removed → 1 failed. Each was followed by a green run with the plugin gone.

## Where the agent pushed back (process evidence)

- course-build twice refused to change a test assertion without an explicit approval record, citing the covenant against editing tests to make an implementation pass. The human supplied D-NFR01-01 with the false-pass evidence, and only then did the edit proceed. This is the intended guardrail behaviour, not a defect.
- course-verify declined to sign off "NFR-01 is delivered", "no official rating on refusal" and "no implicit retries" because the module is not wired into the application. Those claims are recorded as integration debt (TD-10, TD-11) rather than as achieved results.

## Known limitations

- No live model calls were made for NFR-01; the level is a fake-transport count, so live evidence is neither needed nor claimed.
- Classroom-environment friction: the WSL shell returns early for non-interactive sessions, so the API key had to be loaded explicitly; three early plan attempts failed with authorization errors and produced no file changes.
- Integration (graph wiring, C0 mapping, SDK retry configuration, CI collection) is explicitly out of this owner's scope and tracked in the debt register.

## Round 2 - re-baseline to 3d5ce62 (2026-11-16)

The branch was moved from `486a9a5` to `3d5ce62` because a teammate reported that the planning role could not read `docs/README.md` and `docs/review-memo.md`, both mandatory before planning under `Prompt.md` line 37. `1a54b9c` inside the new baseline adds read access for those two files plus `docs/req/product.yaml`. Between the two baselines only `.opencode/opencode.jsonc`, `.opencode/permissions.jsonc` and `docs/architecture/permission-model.md` changed, so the code, the contract and the fixtures were carried over unchanged.

What was redone rather than copied:

- Gate 1 was re-run so that the plan is backed by documents the agent actually read. The round-1 plan had been produced after the human pasted the two refused files into the session, which is not acceptable evidence.
- Gate 4 was re-run on the new revision, and it found three record defects that had survived the round-1 review.

| # | Session | Role | What the human asked | What the agent produced |
| --- | --- | --- | --- | --- |
| 9 | `ses_e1cb0bce4ffeSMiYzgvWzPty3y` | course-plan | Re-plan NFR-01 on 3d5ce62, reading the required documents itself | Read twelve documents with no denial, seven-section plan, four questions, one coverage gap found |
| 10 | `ses_e1caf1566ffeefvZW8dDBgx8mJ` | course-build | D-NFR01-09/10: one appended dispatch-level race test, one docstring line | 66 appended lines (741-806), revision label changed to the contract wording |
| 11 | `ses_e1cab4f89ffed8ePmZwWo5Ljy0` | course-verify | Read-only Gate 4 with human evidence supplied | Conditionally compliant for the owner module, three record defects, five refused reads reported |

Human decisions added in this round: D-NFR01-09 (the appended test is a coverage addition, discrimination proven by mutation, not a defect fix), D-NFR01-10 (docstring carries the contract label, never a bare SHA), D-NFR01-11 (mutation expectations, and the divergence from the round-1 counts must be recorded rather than forced), D-NFR01-12 to D-NFR01-15 (human-run acceptance only, duck-typed prepared request accepted for v1, owner-module-only verdict, exact edit allowlist).

Human-run evidence at 3d5ce62: 39 passed; ruff clean on both files; repository regression 1412 passed, 1 skipped, 1 deselected; `git diff --check` clean. Mutations: capacity guard removed 13 failed, cancel release removed 2, delivery confirmation removed 5, reservation lock removed 2; the module was restored after each run.

Process evidence worth keeping: the build role's first append attempt was refused by the permission layer because edit on the acceptance test is ask-level and a non-interactive run cannot prompt. The run was retried with auto-approval limited to ask-level permissions, under the approval already recorded in the session, and both edits were reviewed line by line afterwards. The role also refused to strengthen the docstring wording without an explicit decision, which is the intended behaviour.
