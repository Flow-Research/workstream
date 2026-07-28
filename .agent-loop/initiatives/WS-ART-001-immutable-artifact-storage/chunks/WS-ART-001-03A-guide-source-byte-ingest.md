# Chunk Contract: WS-ART-001-03A - Guide Source Byte Ingest

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after PLAN2

Artifact contract phase: `guide_source_cutover`

## Goal

Add hidden, authorized guide-source byte ingest through the existing preparation,
admission, put-attempt, verification, and content-publication path without guide
snapshot binding, setup-agent reads, or public activation.

## Allowed Files

- project guide-source ingest models, one migration, repository, schemas,
  service, and router;
- ART guide ingest capability, canonical resource facts/guards, and composition;
- existing prepared-source/admission call sites only for this producer;
- focused migration, authorization, ingest, ambiguity, and API tests;
- backend workflow/agent-gate files only to add and preserve exact coverage;
- related docs and chunk memory.

## Not Allowed

- snapshot binding/activation, setup materialization/continuation, or legacy
  schema removal;
- task/submission/checker/review changes;
- AUTH-owned catalogue/evaluator/grant/identity/matrix/availability edits;
- provider/factory changes, compatibility aliases, or network URL fetching.

## Acceptance Criteria

- authorized caller-supplied/import-pipeline bytes cross `PreparedArtifact` and
  generic admission once; caller hashes and provider references are never truth;
- `ArtifactContent` is published only after complete read-back verification;
- exact retry and ambiguity use existing put/recovery state;
- legacy hash-only/provider-object guide ingest is unavailable on the hidden
  path, but destructive schema removal waits for 03C;
- `artifact.guide_source.ingest` behavior remains fail-closed until AUTH
  activates the exact action after this hidden implementation merges;
- changed subsystem coverage is at least 90 percent and repository coverage
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
```

## Verification

```bash
docker compose up -d --wait postgres redis minio
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_guide_artifacts.py tests/test_artifact_admission.py tests/test_artifact_put_resolution.py tests/test_artifact_verification.py -q --cov=app.modules.projects --cov=app.modules.artifacts --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.
