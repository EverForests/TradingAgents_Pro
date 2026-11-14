# Project covenant

- Extend the baseline with one small owner module per new design responsibility. Add abstractions only where repeated behavior or an approved interface requires them.
- Do not add dependencies, SDKs or providers without human approval and a documented reason. Prefer the standard library and existing integrations.
- Keep tests separate from implementation. Obtain human approval of tests before implementation; include at least one negative test per feature. Do not rewrite a test to make a bad implementation pass.
- Treat publication and dispatch guard code as safety-critical. Changes require a relevant ADR and explicit human approval before editing.
- When a requirement changes, the owner updates architecture, policies, tests and traceability within one sprint; pause any task relying on stale contracts.
