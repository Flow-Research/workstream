# DISCOVERY: WS-CI-001 - Backend CI Acceleration

## Observed current behavior

- `.github/workflows/backend.yml` defines one `test` job with a 240-minute
  timeout, PostgreSQL 16, and a separately started pinned MinIO image.
- `Backend full-suite coverage` invokes
  `backend/scripts/run_isolated_tests.py` with a 12,600-second child timeout.
- The runner creates a unique PostgreSQL role/database, migrates to the single
  Alembic head, buffers child stdout/stderr, redacts database URLs, and cleans up.
- Coverage is produced once and then read by twelve sequential `coverage report`
  commands enforcing the repository-wide 78 percent floor and protected 90
  percent subsystem floors.
- `API contract real API e2e` provisions another isolated database after all
  coverage reports.
- The workflow runs for every pull request and every push to `main`.

## Measured evidence

PR #161 Backend run `29752233451`, job `88385435082`:

| Step | Duration |
|---|---:|
| Runner/service initialization | 17 seconds |
| Dependency installation | 20 seconds |
| Lint and docstring coverage | 1 second |
| Isolated runner self-test | 17 seconds |
| Backend full-suite coverage | 25 minutes 31 seconds |
| All twelve coverage reports | about 2 seconds |
| API contract E2E | 9 seconds |
| Total job | about 26 minutes 42 seconds |

Recent successful Backend workflows have ranged from roughly 24 to 52 minutes.
The full-suite process is therefore the dominant wall-clock cost.

## Repository inventory

- `backend/pyproject.toml` declares pytest, pytest-asyncio, pytest-cov, coverage,
  and Ruff through the existing dev extra; it has no xdist or sharding package.
- `backend/tests/` contains 31 `test_*.py` modules and approximately 999 direct
  test functions before parameter expansion. Pytest's collected node-ID set is
  the executable inventory and may be larger after parameter expansion.
- The largest modules by source size are `test_auth.py`, `test_alembic.py`,
  `test_projects.py`, `test_tasks.py`, and `test_authorization.py`.
- Database-heavy modules construct async engines against the isolated database
  URL. Migration and transaction tests make process-level database separation
  safer than concurrent test processes sharing one database.
- Artifact integration tests use the real MinIO endpoint exposed by the
  workflow.

## Existing tests and gates

- `backend/tests/test_isolated_database_runner.py` proves owned database and
  cleanup behavior.
- `backend/tests/test_coverage_contract.py` protects coverage expectations.
- `scripts/test_agent_gates.py` contains workflow-structure and CI-integrity
  assertions and is the natural place for fail-closed workflow tests.
- `.github/workflows/agent-gates.yml` separately validates merge intent, stale
  wording, Markdown links, loop state, scope, and internal review evidence.
- Branch protection currently receives the Backend job identity `test`; the
  final fan-in must preserve that identity.

## Dependencies and integrations

- GitHub Actions hosted Ubuntu runners.
- PostgreSQL 16 service container.
- Pinned MinIO container image.
- GitHub artifact upload/download actions, which must be pinned by immutable
  commit SHA if introduced.
- Existing coverage data format from pytest-cov/coverage.py.
- MinIO is digest-pinned, but PostgreSQL currently uses the mutable
  `public.ecr.aws/docker/library/postgres:16` tag. Immutable container provenance
  is therefore a target for 01, not an existing property.

## Gaps

- No deterministic shard planner or checked shard manifest exists.
- No exact-once filesystem-module or collected-node-ID proof exists across jobs.
- No coverage-artifact provenance/fan-in validation exists.
- No live per-shard timing evidence exists.
- No current workflow test proves a failed/cancelled shard makes the final
  required job fail.

## Risks discovered

- File size is only a weak runtime proxy; collected test count is a better
  initial deterministic weight but still cannot perfectly balance slow modules.
- `test_alembic.py` may remain a long-tail shard because modules must initially
  remain intact.
- Starting PostgreSQL and installing dependencies per shard increases aggregate
  runner consumption while reducing elapsed time.
- Coverage aggregation is trustworthy only if each artifact is bound to the
  actual checked-out tree, expected shard ID, complete module/node inventory,
  and SHA-256 digest of the exact coverage bytes.
- A final job using unconditional execution must explicitly reject any upstream
  non-success status; GitHub's default dependency skipping is not sufficient for
  a stable required check.

## Unknowns to measure during implementation

- Exact collected node count per module after parameter expansion.
- Actual shard balance on GitHub-hosted runners.
- Whether all shards require MinIO or only the artifact shard.
- Practical concurrency available to the repository/account.
- Aggregate Actions-minute increase for four shards.

## Conventions to preserve

- Immutable action pins and the existing digest-pinned MinIO image; 01 must
  replace the mutable PostgreSQL tag with a reviewed digest pin.
- `run_isolated_tests.py` as the sole database ownership boundary.
- Existing 78/90 coverage floors.
- Backend required check named `test`.
- Full exact-head hosted proof before merge.
- No implementation until a reviewed chunk contract receives human approval.
