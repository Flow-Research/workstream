# Chunk Contract: WS-ART-001-02A3 - ArtifactStore v2 Local Clean Cut

Initiative: `WS-ART-001` | Risk: L1 | Status: Internal review and deterministic evidence passed; external checks pending

Artifact contract phase: `artifact_store_cutover`

## Goal

Atomically replace ArtifactStore v1 with the byte-only v2 contract, migrate
LocalStorage/schema/callers through ADR 0014, and remove dormant Flow Node
configuration. No compatibility path remains after this PR.

## Allowed Files

- `backend/app/interfaces/artifacts.py`;
- `backend/app/interfaces/artifact_operations.py` for the closed product
  capability protocols and request types;
- artifact adapter registration and LocalStorage public adapter surface;
- artifact composition root and `backend/app/core/config.py`;
- artifact models, contracts, repository, and service that own v1 semantics;
- the named Celery scratch-cleanup task, Celery Beat schedule, and API-process
  startup cleanup wiring under `backend/app/workers/` and the composition root;
- one Alembic migration and migration tests;
- focused configuration, factory, LocalStorage, and v2 conformance tests;
- `backend/tests/test_projects.py` only for the real-PostgreSQL cumulative
  `app/workers/*` coverage repair exposed by GitHub CI; no project runtime code;
- `.github/workflows/backend.yml` only to expand the exact 90 percent scoped gate;
- `scripts/check_stale_artifact_contracts.py` only to advance the artifact
  contract phase to `artifact_store_cutover` after the atomic clean cut;
- `scripts/test_agent_gates.py` only to assert the exact workflow command,
  source set, threshold, cumulative retention, and phase binding;
- directly related ADR/spec/glossary/chunk memory.

## Not Allowed

- no S3 SDK, S3 adapter, MinIO, AWS, R2, or Flow Node implementation;
- public or Operator routes or Celery verification/publication jobs;
- guide, task, submission, checker, review, payment, or reputation cutover;
- compatibility alias, dual factory, service locator, plugin discovery, or
  fallback constructor.

## Acceptance Criteria

- ArtifactStore exposes only `put(CommittedArtifactSource)`, read-only
  `observe_put_result(ArtifactCommitment)`, `open`, and `head`;
- LocalStorage implements v2 with exclusive immutable publication, range reads,
  exact replay, bounded async I/O, and sanitized errors. Startup fails closed
  on a single-link provider temporary instead of deleting a possibly live file;
- the migration removes provider retention/receipt semantics, adds immutable
  provider profile/storage namespace, and rebuilds or explicitly refuses
  incompatible pre-production rows;
- one immutable singleton `ArtifactStorageNamespace` stores the canonical
  non-secret namespace fingerprint. Startup and every provider operation
  insert-or-validate it transactionally before I/O; concurrent differing first
  writers prove one winner and one pre-I/O failure. Every replica references it.
  LocalStorage startup requires a pre-provisioned owner-private durable root and
  hashes its normalized path plus filesystem identity, so same-path replacement
  fails before adapter layout mutation. One composition-only bootstrap pins the
  root without layout mutation, PostgreSQL returns a claim for that exact
  namespace identity, and initialization rechecks the path before writing
  through the pinned descriptor. The byte-only `ArtifactStore` does not expose
  this startup lifecycle. v0.1 uses one deployment fence, not a
  per-operation router or hot switch;
- upload state includes `replay_required`; provider acknowledgement creates
  `stored_pending_verification` and `pending/unknown/unknown`, never bindability;
- v1 verify/retain/release/provider-receipt methods are absent from active code;
- backend values are exactly `disabled|local|s3_compatible`; unimplemented
  `s3_compatible` fails typed, `flow_node` is rejected, and local is refused in
  production;
- one active factory path exists; only internal `ArtifactStorageOrchestrator`
  receives writable `ArtifactStore`. Product modules receive only the exact
  guide-ingest, contributor-upload, binding, two-method materialization,
  checker-output, Operator-read, or Operator-recovery protocols. The Operator
  read protocol includes bounded admission-usage inspection; the recovery
  protocol exposes only reason-bound verification retry. AST architecture tests reject raw
  port imports, broad orchestrator injection through FastAPI/Celery composition,
  and provider mutation/observation calls from product modules;
- API-process startup cleanup runs once before accepting artifact work, and a
  named Celery Beat task owns periodic stale-scratch cleanup; both invoke the
  02A2 cleanup service, while neither creates a product claim or review lease;
- focused changed-subsystem coverage is at least 90 percent and repository
  coverage remains at least 78 percent.
- backend CI installs this chunk's exact focused 90 percent gate, preserves
  every earlier scoped 90 percent gate, and retains the exact 78 percent
  repository command below; `scripts/test_agent_gates.py` fails on workflow
  command, source-set, threshold, or cumulative-retention drift.
- the stale artifact-contract marker advances atomically to
  `artifact_store_cutover`, and the phase-binding test rejects any mismatch
  between the active chunk and scanner phase.

## Exact CI Coverage Gate

```bash
coverage report --include='app/adapters/artifacts/*,app/core/cancellation.py,app/core/file_locks.py,app/interfaces/artifact_operations.py,app/interfaces/artifacts.py,app/modules/artifacts/*' --precision=2 --fail-under=90
coverage report --include='app/interfaces/external_services.py' --precision=2 --fail-under=90
coverage report --include='app/core/config.py' --precision=2 --fail-under=90
coverage report --include='app/workers/*' --precision=2 --fail-under=90
coverage report --include='app/main.py' --precision=2 --fail-under=90
```

## Verification

```bash
docker compose up -d --wait postgres redis
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_artifacts.py tests/test_artifact_preparation.py tests/test_config.py tests/test_app.py tests/test_api_controls.py tests/test_artifact_architecture.py tests/test_artifact_cleanup_wiring.py tests/test_artifact_store_conformance.py tests/test_local_artifact_store.py -q --cov=app.adapters.artifacts --cov=app.core.cancellation --cov=app.core.file_locks --cov=app.interfaces.artifact_operations --cov=app.interfaces.artifacts --cov=app.modules.artifacts --cov=app.core.config --cov=app.main --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Is the final port provider-neutral and impossible to pair with an arbitrary
  client-selected digest?
- Did the atomic cut remove every v1 and Flow Node path?
- Is the schema migration honest about incompatible pre-production data?
- Is periodic scratch cleanup owned by one named Celery task and schedule?
