# WS-AUTH-001-10B1 External Review Response

## GitHub Actions run 29872935281

Agent Gates, preflight, API E2E, and shards 1, 2, and 4 passed. Shard 3 failed
after `test_project_role_migration_constraints_and_immutable_history` expected
the former `0031_project_role_grants` head after a successful upgrade. That
assertion stopped before test-owned cleanup, so later migration tests correctly
refused to downgrade the leaked immutable project-role evidence.

Repair `a8a0daef60c1374f103e26c092b59600f5465480` updates exactly three
current-head expectations to `0032_authorization_read_rate`: project-role
schema, outbox schema, and the outbox downgrade transaction that rolls back to
its pre-attempt head. Assertions that intentionally observe a completed
downgrade to, or refusal at, `0031` remain unchanged.

## Repair evidence

- The affected project-role and outbox migration tests pass together, 2/2, in
  a fresh isolated PostgreSQL database.
- Ruff and diff integrity pass.
- Senior engineering, architecture, reuse/dedup, security/auth, QA/test,
  test-delta, product/ops, docs, and CI-integrity tracks re-reviewed the exact
  repair SHA. No actionable finding remains after the metadata update.
- GitHub full shards and aggregate coverage must pass on the pushed repair.

CodeRabbit reported no comments on the initial run; its status was pass with a
rate-limit note.
