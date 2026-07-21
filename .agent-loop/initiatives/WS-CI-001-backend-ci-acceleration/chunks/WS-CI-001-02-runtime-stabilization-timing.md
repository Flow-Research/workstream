# Chunk Contract: WS-CI-001-02 — Migrate-Once Backend Test Runtime

## Parent initiative

`WS-CI-001` — Backend CI Acceleration

## Goal

Remove repeated per-test Alembic migrations, consolidate database isolation
behind one deep fixture, and run dependency-based processes in one CI job with
one PostgreSQL service without weakening tests or coverage.

## Why this chunk exists

Timing evidence showed that sharding was treating the symptom:

- projects spent 589 of 706 seconds in setup and teardown;
- tasks spent 375 of 535 seconds in setup and teardown;
- actor and artifact suites had the same pattern; and
- nine fixtures independently repeated migration and cleanup logic.

The isolated runner already migrates its owned database before pytest starts.
Ordinary fixtures then downgraded and upgraded that same schema for each test.
The source fix is to migrate once and restore an empty data baseline cheaply.

## Risk class

L1

## Allowed files

- `.github/workflows/backend.yml`
- `backend/scripts/run_isolated_tests.py`
- `backend/scripts/run_test_lanes.py`
- `backend/tests/conftest.py`
- test-infrastructure and database-backed files under `backend/tests/`
- `scripts/test_agent_gates.py`
- `docs/operations_backend_testing.md`
- `.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/**`
- `.agent-loop/merge-intents/WS-CI-001-02.json`

## Not allowed

- backend application behavior or production migrations;
- skipping, sampling, reclassifying, or weakening tests;
- lowering the 78 percent repository floor or any protected 90 percent floor;
- using PGlite for lock, trigger, migration, or concurrent transaction proofs;
- shared mutable state between test processes;
- arbitrary weighted shards, cross-job coverage fan-in, or artifact-based
  fallbacks.

## Acceptance criteria

- [x] The isolated runner migrates once per pytest process.
- [x] One central fixture resets all mutable public tables before each
      database-backed test.
- [x] Alembic and immutable actor migration evidence survive every reset.
- [x] Truncate guards are disabled only for the five known guarded tables and
      are re-enabled in the same transaction.
- [x] Module-local migration fixtures are removed.
- [x] Projects, tasks, auth, actors, checkers, audit, authorization, rate
      controls, and artifact admission share the central reset seam.
- [x] The GitHub workflow uses one job, one PostgreSQL service, and one MinIO
      service with four exact dependency lanes and local coverage combine.
- [x] Both runners emit secret-free heartbeats every 60 seconds and bound every
      test process at 20 minutes.
- [x] Every retained backend test executes exactly once.
- [x] The 78 percent repository floor and all protected 90 percent floors remain
      unchanged.
- [x] Local benchmark evidence shows projects and tasks are materially faster
      than the measured sharded baseline.

## Current benchmark evidence

- Cross-module smoke: 9 tests passed in 8.19 seconds.
- Projects: 235 tests passed in 179.53 seconds, down from 706–729 seconds.
- Tasks: 142 tests passed in 145.89 seconds, down from 535–798 seconds.
- Converted database modules: 534 tests passed in 124.21 seconds.
- Schema and reset contracts: 34 tests passed in 178.63 seconds.
- Previous full coverage process: 1,815 tests passed in 919.48 seconds and
  975.62 seconds wall.
- Semantic lanes: all 1,826 tests passed exactly once in 314.40 seconds and
  330.70 seconds wall.
- Lane inventory and failure-custody tests: 11 passed.
- Runner lifecycle: 17 tests passed in 13.52 seconds.
- Real API contract: passed.
- Coverage: 87.58 percent global; protected reports 90.90–100.00 percent.
- PGlite probe: all migrations applied, but `asyncpg` and Alembic hung while
  closing socket connections; PGlite remains unsuitable for the current Python
  and concurrency seam.

## Verification commands

```bash
cd backend
ruff check tests scripts
python -m pytest -q tests/test_isolated_database_runner.py
# Run with a local administrator URL and real MinIO endpoint:
rm -f .coverage .coverage.*
python scripts/run_test_lanes.py \
  --metadata-dir /tmp/workstream-test-lanes \
  --summary-json /tmp/workstream-test-lanes.json \
  --timeout-seconds 1200
coverage combine
cd ..
python -m pytest -q scripts/test_agent_gates.py
```

Local commands above passed. The exact reviewed commit still requires hosted
`Backend / test` proof for the semantic lanes, PostgreSQL, MinIO, API drill, and
every coverage floor.

## Required reviewers

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] CI integrity
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

Whether the reset preserves schema and trigger invariants, whether destructive
migration tests remain isolated, and whether any simplification suppresses
required test or coverage proof.

## Stop conditions

Local implementation and verification are user-directed. Stop before push or PR
if canonical loop state has not recorded a signed start for this chunk.
