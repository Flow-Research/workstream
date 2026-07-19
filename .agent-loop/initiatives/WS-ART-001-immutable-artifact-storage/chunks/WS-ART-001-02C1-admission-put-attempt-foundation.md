# Chunk Contract: WS-ART-001-02C1 - Admission And Put-Attempt Foundation

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 02B1

Artifact contract phase: `artifact_store_cutover`

## Goal

Add the generic durable-byte admission ledger and durable `ArtifactPutAttempt`
state required before any provider write. Keep provider execution, verification,
publication, recovery, Operator routes, and product cutovers inactive.

## Allowed Files

- one artifact-foundation migration;
- artifact admission and put-attempt models, schemas, repository, service, and
  contracts;
- `backend/app/core/config.py` for durable byte limits;
- generic audit repository only when existing audit support is insufficient;
- focused PostgreSQL admission, concurrency, migration, and state tests;
- `.github/workflows/backend.yml` only to expand the exact 90 percent scoped gate;
- `scripts/test_agent_gates.py` only to assert that backend CI retains this
  chunk's exact scoped coverage sources and fail-closed 90 percent threshold;
- directly related operations docs and chunk memory.

## Not Allowed

- provider `put`, observation, verification, publication, or Celery execution;
- recovery-attempt models, Operator/public routes, or manual retry contracts;
- guide, task, submission, checker, or review cutover;
- provider mutation replay, overwrite, delete, retain, or release;
- task-claim or reviewer-lease changes;
- production dispatch or activation.

## Acceptance Criteria

- one generic admission ledger caps cumulative unique provisional/completed
  bytes at every applicable task, producer, project, and deployment scope;
- artifact orchestration accepts a closed guide, contributor, or checker-output
  request and derives all canonical admission scopes after server hashing; no
  caller supplies, removes, or edits a scope collection;
- an admission charge is unique by scope and canonical content identity and
  uses the CAS-protected states `provisional`, `completed`, and `released`;
  provisional and completed charges count, exact replay is deduplicated, and
  concurrent same-content reservations cannot double-charge or oversubscribe;
- Transaction A atomically claims the storage namespace, reserves every charge,
  and creates one `ArtifactPutAttempt` before provider I/O can occur;
- `ArtifactPutAttempt` owns the commitment, namespace, charges, canonical target,
  operation identity, request digest, state, CAS version, timestamps, and the
  nullable executor/lease plus zero-valued execution-generation fields that
  02C2 will claim; this chunk leaves every execution field inactive/unset;
- reservation failure creates no attempt, charge, receipt, audit success, or
  provider call; a committed attempt is the only input a later execution chunk
  may claim;
- this chunk exposes no provider execution path and does not make admission
  mechanics available to product modules;
- migration tests prove fresh, prior-head, populated, and empty round-trip
  behavior;
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
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_artifact_admission.py tests/test_config.py -q --cov=app.interfaces.artifact_operations --cov=app.modules.artifacts --cov=app.modules.audit --cov=app.core.config --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Can any producer bypass or weaken durable-byte admission?
- Is one committed put attempt required before any later provider I/O?
- Does this foundation remain inactive and free of recovery or product behavior?
