# Chunk Contract: WS-ART-001-06A Checker Input And Materialization

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 05

Artifact contract phase: `submission_cutover`

## Goal

Persist post-submit checker input snapshots and reuse the canonical authorized
artifact materializer introduced in 04B to place immutable submission bytes in
bounded isolated checker workspaces.

## Allowed Files

- checker input snapshot/run models, migration, repository, service, and worker;
- artifact binding/read service for checker input roles;
- the existing canonical artifact scratch manager and authorized materializer;
  extension is allowed only for post-submit snapshot integration, never a
  second workspace manager, ledger, quota, or cleanup path;
- checker/artifact call sites consuming exact decisions and service principals
  already delivered by approved WS-AUTH dependencies; no Authorization Service
  owner files;
- focused migration, retry, isolation, integrity, and real-flow tests;
- `.github/workflows/backend.yml` only to expand the exact 90 percent scoped gate;
- `scripts/test_agent_gates.py` only to assert that backend CI retains this
  chunk's exact scoped coverage sources and fail-closed 90 percent threshold;
- related docs and chunk memory.

## Not Allowed

- checker log/output artifact ingestion;
- post-submit review routing or WS-REV implementation;
- reviewer queue, lease, decision, or evidence behavior;
- checker direct access to provider credentials or provider references;
- mutable contributor paths as authoritative input;
- storage failure translated into product decisions or contributor blame.

## Acceptance Criteria

- `CheckerInputSnapshot` commits to submission version, artifact set, exact
  binding/content IDs, hashes/sizes, locked policy/checker versions, and checker
  implementation identity;
- pre-submit and post-submit input prove the same artifact-set hash;
- the post-submit runner receives only authorized immutable Workstream binding
  IDs and reuses the canonical materializer that pre-submit invoked with a
  sealed-ready upload-set source; both are closed forms of the same typed
  materialization request;
- the fixed checker service principal declares
  `artifact.post_submit.checker_input.materialize`, mapped to
  `artifact.checker_input.materialize`; it does not authorize any binding-create
  action;
- each hash and byte count is recomputed during materialization before checker
  execution;
- workspace allocation uses the shared aggregate ledger/quota, private
  no-follow paths, and startup/Celery Beat cleanup ownership; quota exhaustion
  fails closed before execution;
- files are sealed read-only after digest/size verification and before checker
  access; success, failure, cancellation, and crash/stale paths cannot orphan
  confidential bytes;
- transient unavailability leaves the post-submit task in
  `evaluation_pending`; missing/integrity mismatch blocks execution as an
  artifact incident and never becomes a review decision;
- no bytes enter PostgreSQL, Redis, or Celery payloads;
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
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_checker_artifacts.py tests/test_checker_materialization.py tests/test_artifact_scratch_manager.py -q --cov=app.interfaces.artifact_operations --cov=app.modules.checkers --cov=app.modules.artifacts --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Do both checker phases prove the same immutable bytes?
- Can a checker reach provider credentials or arbitrary storage references?
- Is materialization bounded, isolated, and integrity checked?
- Can any post-submit path bypass the exact materializer already used by
  pre-submit or leave a writable/orphaned workspace?
