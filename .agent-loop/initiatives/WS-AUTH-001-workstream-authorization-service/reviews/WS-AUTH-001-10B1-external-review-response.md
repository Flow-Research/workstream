# WS-AUTH-001-10B1 External Review Response

## GitHub Actions run 29872935281

Agent Gates, preflight, API E2E, and shards 1, 2, and 4 passed. Shard 3 failed
after `test_project_role_migration_constraints_and_immutable_history` expected
the former `0031_project_role_grants` head after a successful upgrade. That
assertion stopped before test-owned cleanup, so later migration tests correctly
refused to downgrade the leaked immutable project-role evidence.

Repair `a8a0daef60c1374f103e26c092b59600f5465480` updates exactly three
current-head expectations, now rebased to `0033_authorization_read_rate`: project-role
schema, outbox schema, and the outbox downgrade transaction that rolls back to
its pre-attempt head.

## GitHub Actions run 29875491247

The next refusal matrix proved that the requested `0032` to `0030` migration
is one transactional Alembic downgrade: refusal in `0031` rolls back the
preceding steps and retains the current authorization-read head.
Repair `8ceb4e16d8e152572c94ad3032d8a2edc2cea55e` changes only those two
multi-step refusal-state expectations. The separate successful direct
downgrade-to-`0031` expectation remains unchanged.

## Repair evidence

- The affected project-role schema, refusal-matrix, and outbox migration tests
  pass together, 3/3, in a fresh isolated PostgreSQL database.
- Ruff and diff integrity pass.
- Senior engineering, architecture, reuse/dedup, security/auth, QA/test,
  test-delta, product/ops, docs, and CI-integrity tracks re-reviewed the exact
  repair SHA. No actionable finding remains after the metadata update.
- All nine tracks re-reviewed exact repair SHA `8ceb4e16` and passed.
- GitHub full shards and aggregate coverage must pass on the pushed repair.

CodeRabbit reported no comments on the initial run; its status was pass with a
rate-limit note.

## CodeRabbit final review

CodeRabbit asked for explicit PostgreSQL-version validation because the
migration intentionally compares PostgreSQL-rendered `pg_get_expr` text. The
operations runbook now requires PostgreSQL major version 16, matching CI, and
provides an executable `server_version_num` preflight. Operators must stop and
use a reviewed forward migration change for another major version; they must
not bypass the fail-closed drift check.

Its generated docstring warning reported 33.33 percent, but GitHub preflight's
repository-owned Docstring Coverage gate passed on the exact PR head. No
unrelated docstrings were added to satisfy a contradictory advisory metric.
