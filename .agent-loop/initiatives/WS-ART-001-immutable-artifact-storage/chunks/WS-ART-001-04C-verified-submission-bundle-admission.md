# Chunk Contract: WS-ART-001-04C - Verified Submission Bundle Admission

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 04B

Artifact contract phase: `upload_admission`

## Goal

Consume one passing scratch-bound pre-submit result, write the exact outer ZIP
once through the existing immutable `ArtifactStore` admission path, independently
verify it, and publish one bindable submission-bundle admission.

## Allowed Files

- ART admission orchestration and one submission-bundle admission model/migration
  with the closed `ready|consumed|stale` lifecycle and database constraints;
- existing put-attempt, replica, receipt, verification-job, recovery, scanner,
  and scratch-source integration needed for this producer;
- hidden submission-bundle admission surfaces and ART resource facts/guards;
- focused ambiguity, idempotency, verification, cleanup, API, coverage, docs,
  and chunk-memory changes;
- CI files only to add and preserve the exact scoped 90 percent gate.

## Not Allowed

- a second provider namespace, candidate store, promotion/copy, retention
  window, physical deletion, or new recovery aggregate;
- Submission creation or binding consumption;
- Review, Contribution, compensation, reputation, or delivery behavior;
- AUTH-owned activation changes or larger configured limits.

## Acceptance Criteria

- admission requires the exact unexpired passing result, prepared ZIP
  commitment, semantic manifest, locked task context, actor, and predecessor;
- the predecessor is rechecked under task/version locking before provider I/O;
  drift invalidates the attempt and requires a fresh upload/check;
- initial request authorization occurs before scratch intake; immediately before
  durable capacity/put intent, the owning transaction consumes AUTH's fresh
  prepared capability and typed TASK/PROJECT context capabilities without ART
  importing or locking AUTH-owned tables;
- current actor/identity, project authority, assignment, task, predecessor,
  locked context, canonical resource facts, authorization evidence, capacity,
  and put intent validate/commit atomically; denial or drift causes no provider
  I/O, durable admission, or Submission and cleans scratch;
- the existing generic admission service derives and reserves authoritative
  byte scopes before one conditional `ArtifactStore.put`;
- Workstream persists the put attempt before I/O and uses existing observation,
  receipts, verification jobs, scanners, generation fencing, and recovery;
- background verification, pending-work publication, and ambiguous-put
  resolution retain their distinct fixed service actions
  `artifact.verification.execute`, `artifact.pending_work.scan`, and
  `artifact.put_attempt.resolve`; contributor preparation authority implies none;
- provider acknowledgement alone creates no bindable admission;
- complete provider read-back recomputes ZIP SHA-256 and byte count; only an
  exact match publishes `ArtifactContent`, a ready replica, and one immutable
  `ready` admission bound to preparation actor/identity provenance, project,
  task, assignment, predecessor, exact locked context, manifest, and immutable
  checker-evidence set;
- the admission lifecycle is exactly `ready -> consumed|stale`; only 05 may
  perform either terminal transition and both terminal states are irreversible;
- provider absence, mismatch, ambiguity, or unavailability creates no
  Submission and never becomes checker failure or review state;
- exact replay is idempotent and concurrent replay creates one provider/business
  effect; no `ArtifactOutboxRecoveryAttempt` or receipt-lookup port is added;
- scratch is cleaned after safe source handoff or terminal outcome; if process
  loss occurs before durable put intent, reupload is required; after durable
  intent, existing ART recovery resolves the operation;
- client abandonment may leave a valid unbound `ready` admission; it creates no
  product lifecycle effect and remains charged to existing completed-byte
  scopes alongside terminal `stale`/`consumed` admissions;
- exact preparation replay returns the original admission with no new provider
  write, charge, evidence set, or admission; v0.1 adds no expiry, release,
  deletion, retention process, or cleanup route;
- Operator capacity projections expose bounded counts/bytes for unbound ready
  and stale admissions through existing admission-usage authority;
- after 04A-04C merge their complete hidden manifest, AUTH alone may activate
  `artifact.submission_bundle.prepare`; ART changes no action availability;
- 04C alone declares the hidden contributor route and routable
  `artifact.submission_bundle.prepare` action, mapped by AUTH to
  `submission.create`, with ART-owned task/assignment/actor facts and guards;
  old upload-session actions are never aliases or alternate routes;
- this chunk alone composes the hidden contributor endpoint across the 04A
  intake, 04B checks, and 04C durable handoff in one process-local operation;
  no scratch handle/path is serialized into a later request or Celery payload;
- v0.1 exposes no separate preparation-status GET route; an exact idempotent
  POST retry may return only the same bounded durable operation/admission state
  after a fresh `artifact.submission_bundle.prepare` decision; it never relies
  on the original human authorization evidence;
- revocation after committed put intent does not cancel fixed-service technical
  verification/recovery, but no later Submission consumption inherits the old
  human decision;
- crossed-state tests revoke authority during upload and checker execution and
  prove no durable put/provider I/O; revocation after durable intent permits
  verification only; exact replay and abandoned-ready capacity projections are
  single-effect and bounded;
- focused subsystem coverage is at least 90 percent and repository coverage
  remains at least 78 percent.

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
coverage report --include='app/api/router.py' --precision=2 --fail-under=90
coverage report --include='app/modules/projects/*' --precision=2 --fail-under=90
coverage report --include='app/adapters/project_agents/*,app/interfaces/project_agents.py' --precision=2 --fail-under=90
coverage report --include='app/modules/tasks/*' --precision=2 --fail-under=90
coverage report --include='app/modules/checkers/*' --precision=2 --fail-under=90
```

## Verification

```bash
docker compose up -d --wait postgres redis minio
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_submission_bundle_admission.py tests/test_artifact_put_resolution.py tests/test_artifact_verification.py tests/test_artifact_recovery.py -q --cov=app.modules.artifacts --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Is the exact checked ZIP written once and independently verified?
- Does every ambiguous effect reuse existing ART recovery?
- Can a Submission be created before bindable verification?
