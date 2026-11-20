# Delivery audit — 20 November 2026

## Version and evidence scope

Application/test revision: `df8a9d6419dfa0aab2f4d8986d0a44060354cdb9`. Consolidated documentation baseline: `b8a7564ed9c2ac82d0bab92f548bbe6daea763f3`. The report, presentation and demonstration use these identifiers. Editorial updates do not create a new measured application result.

Five member D5 and D6 collections have been received. The public repository contains GitHub collaborator identities and redacted existing D5 evidence. The restricted submission retains student numbers, full annotated transcripts and original source exports. External submission assembly adds its packaging manifest and presentation derivatives. Each member's agreed weight is 1.00, or 20%; no work-hour estimates are used.

## D7 gate audit

| Course gate | Evidence in the current workflow | Delivery assessment |
| --- | --- | --- |
| Test approval before implementation | OpenCode stops and private approval records provide process evidence. The workflow does not validate an immutable approval timestamp against the first code commit. | Process records exist with feature-specific gaps. A blocking approval gate is not established. |
| Static analysis | Full-repository Ruff, clean-install import and `pip check` run. | Implemented for these checks. No general type-checking job or complete safety-path contract/security/API/permission gate is configured. |
| Schema | JSON Schema, unique requirement IDs, C0–C5/case references and permission-copy equality are checked. | Implemented in the course-artifacts job. |
| Semantic evaluation | Fixed FR-03 paired behavior runs against pinned upstream. Reference selection has offline and live controls. | Scoped evidence exists. A general prompt/model-triggered semantic-quality gate with the declared rubric is not established. |
| Regression | `pytest -q tests test/offline`, a Python matrix and a non-UTC job run. | Implemented for the collected suites and documented optional exclusions. |
| AI-use log | The artifact checker requires a new tool/scope record when application or runtime-prompt paths change. | Implemented for its declared path scope. This is not proof of authorship or prior approval. |
| Branch protection and safety review | Successful Actions receipts exist for the recorded revision. | Hosted required-check rules, enforced human review and accompanying ADR protection have not been independently verified in this documentation pass. |

**D7 compliance verdict: CHANGES REQUIRED.** Successful feature acceptance and recorded CI do not close the missing enforcement requirements. This is a delivery-governance finding, not an assertion of a failing runtime feature. Closing it requires actual configured checks/protection and enforcement evidence, rather than an editorial status change.

## Coordinator disposition — 20 November 2026

The coordinator elected to retain and disclose the D7 gaps rather than implement additional gates in this delivery update. Existing CI scripts, workflows, application behavior and hosted protection settings remain unchanged. No additional OpenCode session or project test run is added for this decision. The documentation publication does not change the CHANGES REQUIRED governance assessment into an approval.

## Source and test packaging

Development retains upstream import paths. The repository and ZIP contain complete application source snapshots under `src/` as well as the runnable root layout, with hashes linking the copies. It retains upstream `tests/`, course `test/offline/` and live `test/live/`. Its D8 source manifest enumerates the submitted modules and test files. The documented suite command selects `tests test/offline` exactly once.

## Evidence boundaries

The integrated regression recorded 1,832 passes, one optional skip, one live-test deselection and 100 passing subtests. The published graph API replay used real cached Yahoo data with live DeepSeek, while the later five-company CLI batch used fresh per-company caches and produced five approved publications. Neither observation measures investment returns, stable model ratings, complete provider coverage or production failure rates. NFR-02 live provider-boundary byte instrumentation remains incomplete.

The current peer-review ring is documented in the review memo. User confirmation of the team workflow establishes responsibility, while actual historical timestamps and submitted GitHub reviews require their own evidence. No missing review is replaced by a fictitious signature.
