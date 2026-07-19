# Chunk Contract: WS-ART-001-02C3 Recovery Attempt And Idempotency Chain

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 02C2

Artifact contract phase: `artifact_store_cutover`

## Goal

Add the durable recovery-attempt envelope and exact idempotent source-job to
retry-job chain without exposing routes or changing product lifecycle state.

## Allowed Files

- one recovery-attempt migration;
- artifact recovery models, schemas, repository, service, and audit contracts;
- internal creation/finalization logic that produces verification retry jobs;
- focused migration, idempotency, concurrency, fencing, and recovery tests;
- `.github/workflows/backend.yml` only to expand the exact 90 percent scoped gate;
- `scripts/test_agent_gates.py` only to assert that backend CI retains this
  chunk's exact scoped coverage sources and fail-closed 90 percent threshold;
- directly related operations docs and chunk memory.

## Not Allowed

- public or Operator routes;
- provider mutation replay, overwrite, delete, retain, or release;
- guide, task, submission, checker, review, payment, or reputation changes;
- a second execution lease on the recovery envelope;
- task-claim or reviewer-lease semantics.

## Acceptance Criteria

- recovery accepts only an exhausted terminal `provider_unavailable` source
  job; all other states create no attempt, retry job, or success audit;
- one transaction creates the recovery envelope, one fresh provider-observation
  verification job, and initiation audit;
- the attempt stores distinct `source_verification_job_id` and
  `retry_verification_job_id`; only the retry job is executable and owns the
  02C2 executor/generation fence;
- idempotency scope is requester, source job, recovery class, and client key,
  with a canonical request digest;
- exact replay returns original attempt/source/retry IDs; changed replay
  conflicts without side effects, including concurrent requests and lost
  responses;
- a lifetime unique source-job constraint prevents different-key or ancestor
  reuse; a later attempt can target only the immediate retry job after that job
  independently exhausts `provider_unavailable`;
- terminal retry result, recovery-envelope result, and terminal audit commit in
  one fenced transaction; stale execution updates zero rows;
- the authorizing requester and fixed Celery service principal remain distinct;
- changed subsystem coverage is at least 90 percent and repository coverage
  remains at least 78 percent;
- backend CI installs this chunk's exact focused 90 percent gate, preserves
  every earlier scoped 90 percent gate, and retains the exact 78 percent
  repository command below; `scripts/test_agent_gates.py` fails on workflow
  command, source-set, threshold, or cumulative-retention drift.

## Exact CI Coverage Gates

```bash
coverage report --include='app/adapters/artifacts/*,app/core/cancellation.py,app/core/file_locks.py,app/interfaces/artifact_operations.py,app/interfaces/artifacts.py,app/modules/artifacts/*' --precision=2 --fail-under=90
coverage report --include='app/interfaces/external_services.py' --precision=2 --fail-under=90
coverage report --include='app/core/config.py' --precision=2 --fail-under=90
coverage report --include='app/workers/*' --precision=2 --fail-under=90
coverage report --include='app/main.py' --precision=2 --fail-under=90
coverage report --include='app/adapters/artifacts/s3_compatible.py' --precision=2 --fail-under=90
coverage report --include='app/core/s3_validation.py' --precision=2 --fail-under=90
coverage report --include='app/modules/audit/*' --precision=2 --fail-under=90
```

## Verification

```bash
docker compose up -d --wait postgres redis minio
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_artifact_recovery.py -q --cov=app.modules.artifacts --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Can any source job produce more than one recovery attempt?
- Can an exact replay ever create a second retry job or audit success?
- Is infrastructure recovery still separate from product claims and review?
