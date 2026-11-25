# Prospective exact-test approvals

New application or governance-script implementation needs an approved tests-only ancestor revision under the installed policy. Retain a plan in `docs/` at that revision. A genuine independent collaborator submits APPROVED on its PR before the first implementation commit. The implementation PR adds a JSON receipt with `test_revision`, `plan_path`, `approval_pr`, and exact `implementation_paths`; consult `d7_policy.check_prior_approval` for the executable format. Approved tests cannot subsequently be edited in that implementation patch. Separate tests-only review makes the timing auditable.

This directory contains no fabricated historical approval. A role switch, coordinator assignment, mutable PR body or retrospective signature is not the required GitHub review event. Governance-only first installation has a bounded documented exception because its base does not yet contain the policy; later implementation does not inherit that exception.
