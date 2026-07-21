# PLAN: WS-CI-001 - Backend CI Acceleration

## Objective

Reduce Backend workflow wall-clock time without test sampling, arbitrary
weighted shards, weaker coverage, or weaker PostgreSQL contract evidence.

## Selected design

### 1. Dependency-based process lanes

`backend/scripts/run_test_lanes.py` assigns every test module exactly once to the
no-PostgreSQL, schema-contract, control-plane, or execution-plane lane. All four
processes run concurrently in one job and write private coverage files. The
three database lanes share one PostgreSQL server but invoke
`run_isolated_tests.py` with independent temporary databases and roles. Both
runners emit secret-free heartbeats and bound every lane at 20 minutes.

### 2. Cheap isolation for ordinary tests

`backend/tests/conftest.py` owns the normal database reset. Before each
database-backed test it disposes pooled connections and truncates all mutable
public tables in one transaction while preserving:

- `alembic_version`;
- immutable `actor_profile_migration_state` evidence; and
- the schema, constraints, and triggers installed by migrations.

The fixture temporarily disables only the five known truncate guards, restores
the baseline `authority_control` row, and re-enables every guard in the same
transaction. Route and service modules do not run Alembic.

### 3. Explicit PostgreSQL schema-contract lane

Tests marked `postgres_schema_contract` own whole-schema Alembic transitions.
They receive a rebuilt head schema rather than the truncate reset and restore
`head` during teardown. This intentionally slower path is limited to migration
contracts. Lock, trigger, deferred-constraint, `asyncpg`, and concurrent
transaction proofs remain on real PostgreSQL.

PGlite is not adopted for the Python suite. The schema migrated in the spike,
but the socket multiplexer did not close `asyncpg` connections reliably and does
not guarantee production PostgreSQL concurrency behavior.

### 4. One required GitHub job

The required context remains `Backend / test`. One job provides one PostgreSQL
service and one MinIO service, then runs in this order:

1. internal evidence, lint, docstrings, and isolated-runner tests;
2. four semantic processes with exact module inventory validation;
3. local coverage combine and the destructive real API contract drill;
4. the unchanged 78 percent repository floor and every protected 90 percent
   floor.

There is no GitHub matrix, arbitrary planner, timing artifact, or cross-job
fan-in. Product tests execute exactly once across the lanes; runner lifecycle
tests execute once in their dedicated prerequisite step.

## Correctness boundaries

- No skipped, sampled, or reclassified product tests.
- No mutable database is shared between pytest processes.
- No production database is accepted by the isolated runner.
- No database URL, password, MinIO credential, or environment dump enters logs
  or metadata.
- Destructive migration tests remain serialized by the database-scoped DDL lock.
- Coverage cannot compensate for a failed test or API contract drill.

## Local verification

- Cross-module smoke: 9 passed in 8.19 seconds.
- Projects: 235 passed in 179.53 seconds, down from 706–729 seconds.
- Tasks: 142 passed in 145.89 seconds, down from 535–798 seconds.
- Converted database modules: 534 passed in 124.21 seconds.
- Schema/reset contracts: 34 passed in 178.63 seconds.
- Semantic lanes: 1,826 passed exactly once in 314.40 seconds; 330.70 seconds
  including process startup and local coverage combine.
- Previous single process: 1,815 passed in 919.48 seconds; 975.62 seconds wall.
- Lane inventory and failure-custody tests: 11 passed.
- Isolated-runner lifecycle: 17 passed in 13.52 seconds.
- Agent workflow gates: 91 passed.
- Real API contract drill: passed.
- Coverage: 87.58 percent global; protected reports range from 90.90 to
  100.00 percent.
- Ruff and `git diff --check`: passed.

Hosted timing and exact checked-out-commit proof remain required before claiming
the GitHub workflow result.

## Rollback

If semantic lanes violate exact execution or resource isolation, revert the lane
runner and workflow invocation while retaining the central reset. Restore
correctness through one isolated runner; do not lower coverage, skip tests, or
add arbitrary weighted shards to hide fixture cost.

## Delivery state

`WS-CI-001-02` supersedes the earlier shard/fan-in implementation. Local
implementation and proof are complete under the user's direction. Push or PR is
still prohibited until canonical loop state records an explicit signed start for
this chunk.
