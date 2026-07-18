# Chunk Contract: WS-QUAL-001-01A Isolated Database Runner

Status: merged through PR #103 as
`2901a3ebe68b7c770ccb1ff06841d79ce0c20d94` on 2026-07-12.

## Goal

Provide one safe local Postgres provisioner so concurrent worktrees and CI jobs
run the complete backend suite without shared mutable database state or exposing
admin authority to test children.

## Risk and scope

- Risk: L1 database/test infrastructure
- Implementation cap: 700 changed lines; later chunks retain 500
- Allowed: `backend/tests/conftest.py`, `backend/tests/test_api_contract_e2e.py`,
  `backend/tests/test_isolated_database_runner.py`,
  `backend/scripts/run_isolated_tests.py`,
  `backend/scripts/api_contract_e2e.py`, `backend/scripts/week2_api_e2e.py`,
  `.github/workflows/backend.yml`, `docs/operations_backend_testing.md`, and
  WS-QUAL/global loop memory.
- Forbidden: `backend/app/**`, migrations, coverage dependencies/policy/floor/
  evidence, API/schema changes, test skips, weakened assertions, or nonlocal DBs.

## Acceptance criteria

- Parent accepts only `WORKSTREAM_TEST_ADMIN_DATABASE_URL` with exact
  `postgresql+asyncpg` scheme, loopback host, and existing admin database.
- Each invocation creates a strict unique database and strict unique ephemeral
  login. The login owns only that database and has no superuser, create-role,
  create-database, replication, or bypass-RLS authority. Child target URLs use
  only the ephemeral credential; admin credentials and authority remain parent-only.
- Destructive helpers revalidate identifiers at point of use. Create collision
  cleans only the newly owned role and never terminates, attaches to, or drops
  the existing database or its sessions.
- The owned database is migrated to exactly one repository Alembic head before
  child launch. Migration failure never launches the child.
- Child env removes admin/nonlocal variables and overwrites test/runtime URLs.
  Complete admin and target URLs are redacted from output; metadata contains
  only schema version, database name, observed Alembic head, and current HEAD.
- Cleanup terminates exact ephemeral-role/database sessions, drops the database
  and role, fails closed on cleanup error, and runs after success, nonzero exit,
  timeout, SIGINT, or SIGTERM.
- Real Postgres tests prove absence/presence/absence, concurrent uniqueness,
  least privilege, migration, collision session survival, exact cleanup, exit
  propagation, timeout/interruption cleanup, and credential redaction.
- CI uses two explicit phases: lifecycle tests run with the parent admin DSN;
  every other test runs inside one provisioned database. Together they collect
  every test exactly once. The API drill retains its dedicated local test DB.
- The runbook documents env-only credentials, the exact two-phase local/CI
  commands, cleanup/redaction, API drill safety, and troubleshooting.

## Verification

```bash
(cd backend && .venv/bin/python -m pip check)
(cd backend && .venv/bin/python -m ruff check tests scripts)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python -m pytest -q tests/test_isolated_database_runner.py)
(cd backend && tmp_dir=$(mktemp -d) && trap 'rm -rf "$tmp_dir"' EXIT && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$tmp_dir/database.json" -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Review and stop

Required tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta. Stop on production
changes, admin credentials in a child, shared mutable DB state, skipped tests,
or more than 700 implementation lines. Do not start `WS-QUAL-001-01B`.
