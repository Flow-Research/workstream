# Chunk Contract: WS-ART-001-02C2 - Verification Publication And Fencing

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 02C1

Artifact contract phase: `artifact_store_cutover`

## Goal

Claim committed put attempts, perform provider writes and read-only outcome
observation, publish complete-object verification, and fence Celery execution.
Do not add recovery attempts, Operator routes, or product cutovers.

## Allowed Files

- one verification/fencing migration;
- artifact verification models, schemas, repository, service, and contracts;
- artifact orchestration execution for committed put attempts;
- Celery put-resolution/verification tasks and periodic publication scanner;
- `backend/app/core/config.py` for scanner SLA, execution lease,
  complete-read deadline, and persistence margin;
- focused PostgreSQL/Celery/artifact tests;
- `.github/workflows/backend.yml` only to expand the exact 90 percent scoped gate;
- `scripts/test_agent_gates.py` only to assert that backend CI retains this
  chunk's exact scoped coverage sources and fail-closed 90 percent threshold;
- directly related operations docs and chunk memory.

## Not Allowed

- recovery-attempt models, Operator/public routes, or manual retry contracts;
- guide, task, submission, checker, or review cutover;
- provider mutation replay, overwrite, delete, retain, or release;
- task-claim or reviewer-lease changes;
- production dispatch before AUTH registers the exact planned actions and
  static service-action matrix, provisions the exact service ActorProfiles and
  ActorIdentityLinks, admits them through AUTH-09E, 02C2/02D merge hidden
  behavior/resource composition, and the later AUTH activation checkpoint
  integrates their evaluators.

## Acceptance Criteria

- only artifact orchestration can claim a committed `ArtifactPutAttempt` and
  invoke writable `ArtifactStore`; architecture tests reject raw-port imports,
  broad orchestrator injection, and provider calls from product modules;
- provider acknowledgement yields `stored_pending_verification`, never a
  bindable replica;
- a claimed attempt gains a fresh executor UUID, PostgreSQL-clock lease expiry,
  and atomically incremented execution generation before provider I/O;
- provider acknowledgement or a fresh complete-object observation completes
  provisional charges; ambiguous outcomes remain provisional, authoritative
  absence releases charges and requires caller replay, and replay atomically
  reacquires released capacity before a later provider write;
- confirmed, quarantined, or integrity-mismatched content remains completed and
  charged because v0.1 has no physical deletion;
- a bounded scanner publishes prepared, acknowledgement-unknown, and expired
  in-flight attempts; duplicate publication is harmless;
- the resolver calls only read-only `observe_put_result` with the persisted
  commitment and then performs a fresh complete-object read and Workstream
  SHA-256/byte-count verification; no background path replays a write;
- matching bytes complete Transaction B once; absence releases charges and
  requires caller replay; mismatch quarantines;
- terminal put-resolution and verification writes require matching executor and
  generation plus current service actor/link/action/resource authority
  revalidated in the same terminal transaction; stale or revoked executors
  write no state, receipt, replica, recovery, or audit fact;
- the result matrix handles verified, missing, integrity mismatch, provider
  unavailable, conflict, and stale executor outcomes;
- missing yields `missing/unavailable/unknown`; integrity mismatch yields
  `integrity_mismatch/available/invalid` and cannot reset;
- complete reads enforce a total deadline shorter than the lease by a tested
  persistence margin, including continuously progressing slow streams;
- mechanics remain inactive through 02D while ART builds and tests hidden
  resource/behavior composition; only the later AUTH internal-action activation
  checkpoint can make them executable;
- migrations prove fresh, prior-head, populated, and empty round-trip behavior;
- changed subsystem coverage is at least 90 percent and repository coverage
  remains at least 78 percent;
- backend CI preserves every earlier scoped 90 percent gate and the exact 78
  percent repository command; gate tests fail on command, source-set,
  threshold, phase, or cumulative-retention drift.

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
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_artifact_verification.py tests/test_config.py -q --cov=app.interfaces.artifact_operations --cov=app.modules.artifacts --cov=app.modules.audit --cov=app.core.config --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Is provider execution impossible without a committed admission/put attempt?
- Can any stale or duplicate Celery executor write terminal state?
- Is verification independent of upload acknowledgement and write replay?
