# Architecture risks and review triggers

Current document review: **Approved**, recorded on 21 November 2026. [Offline review record](../governance/offline-review-20261121.md) distinguishes current acceptance from historical implementation approvals and separate hosted review.

| ID | Assumption or exposure | Impact | Owner | Mitigation and review trigger |
| --- | --- | --- | --- | --- |
| R-01 | A reference can resolve without semantically supporting its argument. | A formally valid chain can accompany weak reasoning. | FR-01 owner | State the reference-integrity scope. Introduce a labelled support rubric before making faithfulness claims. |
| R-02 | External market/news services can rate-limit or return unusable history. | Analysis can complete without admissible publication evidence. | Integration coordinator | Preserve missing reasons and fail closed. Review on a new provider failure pattern. |
| R-03 | Concurrent yfinance cold-cache initialization can lock SQLite. | Snapshot tool can fail before HTTP access. | Integration coordinator | Retain stack and dependency versions; distinguish cache locks from HTTP 429. Review on recurrence or dependency changes. |
| R-04 | A provider adapter may change message serialization or retry behavior. | Byte measurements or request accounting can drift. | NFR-01 and NFR-02 owners | Re-run transport, pairing and zero-debit controls on adapter changes. |
| R-05 | Optional source absence can be mistaken for whole-run failure or numeric neutrality. | Misleading downstream interpretation. | FR-03 owner | Use authoritative coverage and nullable assessment; preserve positive neutrality controls. |
| R-06 | Checkpoint restoration could reset spent requests. | A resumed run could exceed its original quota. | NFR-01 owner | Metered profile disables resume; restoration requires a revised contract and adversarial tests. |
| R-07 | Dependency updates alter indicators. | Frozen metric fixtures may fail or silently compare different definitions. | FR-02 owner | Record stockstats version and separate operand precision from display rounding. |
| R-08 | Historical approval records and hosted enforcement are incomplete. | Course process compliance cannot be established from a green build. | Coordinator and assigned reviewers | Preserve actual records and audit each D7 gate separately. Current approval does not establish earlier approval. |
| R-09 | Raw sessions contain credentials or personal metadata. | Disclosure through a public commit or submission artifact. | Each member and coordinator | Restrict raw materials, scan copies before packaging, and exclude local environment files. |

These are reviewable exposures, not measured production failure rates. [Debt register](../debt-register.md) tracks current actions; [live acceptance](../live-acceptance.md) records observed failures.
