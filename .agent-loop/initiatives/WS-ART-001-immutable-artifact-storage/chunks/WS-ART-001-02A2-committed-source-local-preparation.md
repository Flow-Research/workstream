# Chunk Contract: WS-ART-001-02A2 - Committed Source And Local Preparation

Initiative: `WS-ART-001` | Risk: L1 | Status: Active after explicit user start on 2026-07-15

Artifact contract phase: `foundation`

## Goal

Add the bounded `PreparedArtifact`/`CommittedArtifactSource` boundary and
refactor LocalStorage byte/file internals so the later v2 cutover is small. The
active ArtifactStore v1 contract and runtime behavior remain unchanged.

## Allowed Files

- new provider-neutral committed-source and scratch-preparation modules under
  `backend/app/modules/artifacts/`;
- shared bounded I/O primitives in `backend/app/core/cancellation.py` and
  `backend/app/core/file_locks.py`, with minimal adoption by artifact
  preparation, the existing ingest service, and LocalStorage private ownership
  handoffs;
- LocalStorage private byte/file helpers only, while preserving its active v1
  public behavior;
- artifact preparation and private operation-lock settings in
  `backend/app/core/config.py`, plus the single composition-root pass-through
  to LocalStorage;
- focused preparation, concurrency, filesystem-safety, and LocalStorage tests;
- `.github/workflows/backend.yml` only to expand the exact 90 percent scoped gate;
- `scripts/test_agent_gates.py` only to assert the exact workflow command,
  source set, threshold, and cumulative retention;
- directly related ADR/spec/glossary/chunk memory.

## Not Allowed

- changing the active ArtifactStore interface, provider selection, or factory
  path; the private LocalStorage lock-timeout setting may be passed through the
  existing branch without adding another path;
- schema or Alembic changes;
- no S3 SDK, provider configuration, MinIO, AWS, R2, or Flow Node;
- product routes or guide/task/submission/checker/review cutovers;
- compatibility adapter, second active factory path, or fallback constructor.

## Acceptance Criteria

- every initially uncommitted source can be written once to private bounded
  scratch while Workstream computes SHA-256 and exact byte count;
- the new inactive preparation boundary compares any supplied client
  digest/size commitment before a future v2 provider call; active v1 runtime
  remains unchanged until the `02A3` clean cut;
- only the preparation service can construct a sealed
  `CommittedArtifactSource`, whose stream and server-computed commitment cannot
  be paired independently;
- a database-independent cross-process filesystem ledger under the dedicated
  private scratch root reserves the full 512 MiB maximum before file
  creation and enforces aggregate bytes, files, concurrency, free-space floor,
  deadline-before-TTL, locked cleanup, and no-follow/private-file behavior;
- scratch coordination never uses PostgreSQL, Redis, product records, or the
  durable artifact-storage namespace;
- tests include concurrent processes, quota and disk exhaustion, cancellation,
  crash cleanup, symlink/non-regular rejection, and adversarial client digest
  mismatch with zero provider calls;
- this chunk implements deterministic stale-scratch discovery and cleanup
  mechanics only; it does not activate startup or periodic cleanup ownership;
- LocalStorage's active v1 observable behavior is unchanged;
- focused changed-subsystem coverage is at least 90 percent and repository
  coverage remains at least 78 percent.
- backend CI installs this chunk's exact focused 90 percent gate, preserves
  every earlier scoped 90 percent gate, and retains the exact 78 percent
  repository command below; `scripts/test_agent_gates.py` fails on workflow
  command, source-set, threshold, or cumulative-retention drift.

## Exact CI Coverage Gate

```bash
coverage report --include='app/adapters/artifacts/*,app/core/cancellation.py,app/core/file_locks.py,app/interfaces/artifact_operations.py,app/interfaces/artifacts.py,app/modules/artifacts/*' --precision=2 --fail-under=90
coverage report --include='app/interfaces/external_services.py' --precision=2 --fail-under=90
coverage report --include='app/core/config.py' --precision=2 --fail-under=90
```

## Verification

```bash
docker compose up -d --wait postgres redis
(cd backend && .venv/bin/ruff check app tests)
(cd backend && .venv/bin/pytest tests/test_artifact_preparation.py tests/test_local_artifact_store.py tests/test_config.py -q --cov=app.core.cancellation --cov=app.core.file_locks --cov=app.modules.artifacts.preparation --cov=app.modules.artifacts.sources --cov=app.core.config --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Can a caller choose a content-addressed key without supplying those bytes?
- Are scratch limits safe across multiple API/Celery processes?
- Did this remain a preparatory refactor rather than a second runtime path?
- Are cleanup mechanics testable without silently activating a new worker?

## Cross-Initiative Compatibility

Read-only audits against the active authorization, review, and contribution
worktrees establish these boundaries:

- this chunk performs no authorization and declares no actor, action,
  permission, resource, grant, or service-principal authority;
- later active artifact operations must use canonical `ActorProfile.id` and the
  authorization service's closed action, permission, and service-identity
  contracts;
- WS-REV continues to own reviewer packet/evidence records and receives only
  verified Workstream `ArtifactBinding` references through future narrow
  capabilities, never this scratch boundary or a concrete adapter;
- WS-CON's proposed contribution-evidence capabilities and action are a future
  separately approved ART prerequisite. They are intentionally not implemented
  or frozen by `02A2`.
