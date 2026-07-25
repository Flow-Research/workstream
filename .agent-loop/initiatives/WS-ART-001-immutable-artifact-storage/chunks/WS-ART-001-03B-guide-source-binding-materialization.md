# Chunk Contract: WS-ART-001-03B - Guide Source Binding And Materialization

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 03A and exact AUTH activation

Artifact contract phase: `guide_source_cutover`

## Goal

Bind verified guide-source content to snapshot items and give setup agents one
authorized, provider-neutral, integrity-checking read/materialization capability
without performing the legacy schema cutover.

## Allowed Files

- guide snapshot/item binding models, one migration, repository, schemas, and service;
- ART guide read/binding capability and canonical resource facts/guards;
- existing artifact scratch manager/materializer integration for setup input;
- setup-agent input assembly consuming the typed ART capability;
- focused migration, authorization, binding, materialization, and integrity tests;
- backend workflow/agent-gate files only to add and preserve exact coverage;
- related docs and chunk memory.

## Not Allowed

- contributor submission/checker/review behavior;
- direct provider access, URL fetching, a second materializer/scratch manager,
  setup policy decisions, or destructive legacy-field removal;
- AUTH-owned catalogue/evaluator/grant/identity/matrix/availability edits.

## Acceptance Criteria

- snapshot items bind exact verified `ArtifactContent` without circularly making
  the item both the source and authority for that content;
- snapshot/bundle identity commits to ordered content identities and descriptors;
- setup agents receive bounded bytes/manifests only through ART and every full
  read recomputes SHA-256 and byte count;
- missing/mismatched bound bytes are artifact incidents, not guide insufficiency;
- fixed guide read/binding actions remain fail-closed until AUTH activation;
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
coverage report --include='app/adapters/project_agents/*,app/interfaces/project_agents.py' --precision=2 --fail-under=90
```

## Verification

```bash
docker compose up -d --wait postgres redis minio
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_guide_artifacts.py tests/test_project_setup.py tests/test_checker_materialization.py tests/test_artifact_scratch_manager.py -q --cov=app.modules.projects --cov=app.modules.artifacts --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.
