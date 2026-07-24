# Chunk Contract: WS-ART-001-03C - Guide Source Cutover And Continuation

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 03B and exact AUTH activation

Artifact contract phase: `guide_source_cutover`

## Goal

Remove legacy guide-source identity, make verified ART bindings authoritative,
and resume the exact same setup generation after artifact recovery without
adding a Project Manager resume command.

## Allowed Files

- guide-source/snapshot models, one clean-cut migration, repository, schemas,
  service, and router;
- exact same-generation setup continuation record/worker and affected setup tasks;
- `backend/scripts/api_contract_e2e.py` only for the guide clean cut;
- focused refusal, continuation, recovery, API, and real-flow tests;
- stale-contract/agent-gate/backend workflow files only for the exact phase and
  preserved coverage gates;
- related docs and chunk memory.

## Not Allowed

- task/submission/checker/review cutover, synthetic backfill, URL fetching,
  provider/factory changes, or Project Manager resume command;
- AUTH-owned catalogue/evaluator/grant/identity/matrix/availability edits.

## Acceptance Criteria

- migration refuses unsafe populated legacy rows rather than fabricating bytes;
- caller `content_cid`, provider-object schemes, and hash-only identity are
  removed without aliases after verified replacement is available;
- recovery continuation references a persisted setup run/generation and resumes
  only when project, guide, snapshot, policy, and generation still match;
- Operator recovery authorization and automatic setup continuation remain
  distinct audit facts; neither approves guide sufficiency;
- changed guide bytes create a new snapshot/setup generation, while locked tasks
  retain their prior context unless explicitly rebased;
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
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_projects.py tests/test_project_setup.py tests/test_guide_artifacts.py tests/test_artifact_recovery.py -q --cov=app.modules.projects --cov=app.modules.artifacts --cov=app.workers --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py)
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.
