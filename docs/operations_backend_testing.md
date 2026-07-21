# Backend Testing Operations

Workstream groups backend tests into four dependency-based processes. The
no-PostgreSQL lane runs without database credentials. Three PostgreSQL lanes
share one server but each owns a temporary database and role. Every database is
migrated once; fixtures then restore an empty baseline with `TRUNCATE`.

## Local full suite

Keep the administrator URL in the environment with `postgresql+asyncpg` and a
loopback host. Never place real or shared credentials in arguments, logs,
evidence, or configuration.

```bash
cd backend
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
export WORKSTREAM_TEST_ADMIN_DATABASE_URL='postgresql+asyncpg://USER:PASSWORD@localhost:5433/postgres'
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
.venv/bin/python -m pytest -q tests/test_isolated_database_runner.py
rm -f .coverage .coverage.*
.venv/bin/python scripts/run_test_lanes.py \
  --metadata-dir "$tmp_dir/lanes" \
  --summary-json "$tmp_dir/summary.json" \
  --timeout-seconds 1200
.venv/bin/coverage combine
unset WORKSTREAM_TEST_ADMIN_DATABASE_URL
```

`run_test_lanes.py` validates that every `test_*.py` module is assigned exactly
once or is the dedicated runner test. It starts the no-PostgreSQL, schema,
control-plane, and execution-plane processes concurrently. Each process writes a
private coverage file; coverage is combined locally after every lane passes.

Database lanes invoke `run_isolated_tests.py`, which removes the administrator
URL before pytest, overwrites child database URLs, and redacts complete URLs.
Both runners emit secret-free 60-second heartbeats. The isolated runner drops
each owned database and role after success, failure, timeout, or interruption.

## Database reset model

`tests/conftest.py` owns the reset seam. Before each database-backed test it:

1. disposes pooled application connections;
2. truncates every mutable public table in one transaction;
3. preserves `alembic_version` and immutable actor migration evidence;
4. restores the single `authority_control` baseline row; and
5. re-enables the five explicit truncate guards.

Do not add module-local migration fixtures. Migration behavior belongs in
`tests/test_alembic.py`; ordinary route and service tests must consume the
central clean-database fixture.

PGlite is not the default Python test adapter. The full schema migrates on
PGlite, but the current PGlite Socket multiplexer does not complete
`asyncpg.Connection.close()` reliably and does not guarantee normal PostgreSQL
concurrency behavior. Lock, trigger, migration, and concurrent transaction
proofs therefore remain on real PostgreSQL.

## Focused checks

The API-guard tests are statically database-free:

```bash
.venv/bin/python -m pytest -q tests/test_api_contract_e2e.py
```

Runner lifecycle tests require the administrator environment variable:

```bash
.venv/bin/python -m pytest -q tests/test_isolated_database_runner.py
```

Run the destructive API drill only through the isolated runner or against a
strict local test database name:

```bash
WORKSTREAM_DATABASE_URL='postgresql+asyncpg://USER:PASSWORD@localhost:5433/workstream_test' \
  .venv/bin/python scripts/api_contract_e2e.py
```

Do not use `WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE` for ordinary proof.

## Latest local proof

The semantic lanes executed all 1,826 tests exactly once in 314.40 seconds;
including process startup and local coverage combine, wall time was 330.70
seconds. The previous single process required 919.48 test seconds and 975.62 wall
seconds. Global coverage is 87.58 percent; protected reports are
90.90–100.00 percent. The real API contract drill also passed.

An AST audit found no exact duplicate test bodies. Six literal-only similarity
clusters are candidates for parametrization, but parametrization would preserve
the same executions and would not materially reduce runtime. No behavior test
was removed; only Outbox's repeated Alembic-head setup was deleted.

These values prove the local test topology, not hosted runner timing. Use the
exact checked-out commit's `Backend / test` result for release evidence.

## Hosted proof

The required GitHub check remains `Backend / test`. It uses one job, one
PostgreSQL service, and one MinIO service. Its order is:

1. internal evidence, lint, docstrings, and isolated-runner checks;
2. four dependency-based test processes with isolated mutable state;
3. local coverage combine followed by the destructive API contract drill; and
4. the 78 percent repository floor plus every protected 90 percent floor.

There is no GitHub matrix, arbitrary weighted shard, cross-job artifact fan-in,
or shared mutable database. Every lane has a 20-minute bound, the API drill has
a 10-minute bound, and the GitHub job has a 45-minute hard bound.

### Failure diagnosis

- **Runner test:** inspect provisioning, redaction, signal, or cleanup behavior.
- **Semantic lanes:** inspect the named lane result and 60-second active-lane
  heartbeat; every process is force-bounded at 20 minutes.
- **API drill:** inspect the named contract assertion after the full suite.
- **Coverage:** inspect the named global or protected subsystem report. Coverage
  cannot compensate for a failed test or API drill.

Rerun the complete `Backend / test` job for the same checked-out commit. Never
lower coverage, skip tests, or restore parallel databases to hide fixture
regressions.
