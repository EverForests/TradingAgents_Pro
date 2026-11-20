# Public repository and private submission

The course PDF requires a real GitHub repository and the D1–D9 artifact structure but does not explicitly prescribe public visibility. The coordinator selected a de-identified public version before publication on 20 November 2026.

| Content | Public repository | Restricted course submission |
| --- | --- | --- |
| Application and tests | Same implementation revision | Same implementation revision |
| Requirements, architecture and governance | Shared engineering content | Same shared engineering content |
| Contributor identifiers | GitHub collaborator accounts | Registered names and student numbers |
| Report/reflections | GitHub account labels | Complete course identifiers |
| D5 | Redacted derivatives of existing annotated records | Complete originals and original hashes |
| Presentation and packaging derivatives | Excluded | Retained externally with delivery material |

No additional agent sessions were created. The original session evidence is preserved privately. Public derivatives mask student numbers, direct contact details, local home paths and credential-like material. Public hashes describe the redacted files rather than claiming identity with the originals. Credentials, environment files, account state, caches and virtual environments remain excluded from both distributions.

The unpublished unredacted local commit is replaced before push, so its original payload is not introduced into remote history. GitHub visibility, application behavior and CI configuration are unchanged. [D7 gaps](delivery-readiness.md#d7-gate-audit) remain documented.
