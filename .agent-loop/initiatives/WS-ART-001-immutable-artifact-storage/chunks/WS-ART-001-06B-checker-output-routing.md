# Chunk Contract: WS-ART-001-06B Checker Output And Post-Submit Routing

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 06A

Artifact contract phase: `checker_cutover`

## Goal

Ingest checker logs and generated outputs as canonical verified artifacts and
persist checker completion facts before preserving the existing checker-owned
lifecycle route. The task remains `evaluation_pending` only while execution or
infrastructure retry is active. This chunk creates no review aggregate, queue,
lease, assignment, or decision.

## Allowed Files

- checker result/log/output models, migration, repository, service, and worker;
- prepared-artifact ingestion and binding for checker log/output roles;
- the persisted checker-completion facts and artifact bindings consumed by the
  existing checker lifecycle route and, later, WS-REV;
- checker/artifact call sites consuming exact decisions and service principals
  already delivered by approved WS-AUTH dependencies; no Authorization Service
  owner files;
- focused migration, retry, crash, isolation, routing, and real-flow tests;
- `.github/workflows/backend.yml` only to expand the exact 90 percent scoped gate;
- `scripts/test_agent_gates.py` only to assert that backend CI retains this
  chunk's exact scoped coverage sources and fail-closed 90 percent threshold;
- `scripts/check_stale_artifact_contracts.py` and its focused tests only to
  advance the marker to `checker_cutover`;
- related docs and chunk memory.

## Not Allowed

- reviewer queue/lease/decision implementation owned by WS-REV;
- reviewer evidence upload;
- direct provider references or credentials in checker outputs;
- storage failure translated into `needs_revision`, reject, payment,
  contribution, or reputation effects;
- project-specific Terminal Benchmark behavior.

## Acceptance Criteria

- checker logs and generated outputs use the same bounded prepared-artifact
  path, are independently verified, and bind to the exact checker run;
- checker output ingest reserves task, project, fixed checker-service-principal,
  and deployment byte charges through the generic 02C1 admission service. It
  never consumes or attributes the contributor actor's quota and does not own a
  checker-specific quota ledger;
- checker output ingestion requires `artifact.checker_output.write`, and its
  resulting immutable binding declares `artifact.checker_output.binding.create`,
  targets the canonical checker-run resource, and maps separately to
  `artifact.binding.create`;
- reservations are cross-process, bounded, deadline constrained, and cleaned
  only when expired; slow-active, cancellation, and crash cases are tested;
- non-reproducible crash replay fails the old checker attempt and uses a new
  attempt identity;
- the project `PostSubmitCheckerPolicy` selects project checks and non-bypassable
  Workstream defaults remain included;
- transient provider failure keeps `evaluation_pending` and uses checker
  infrastructure retry; it creates no product decision;
- after checker outputs and completion facts commit atomically, the existing
  checker contract routes contributor-fixable blocking failures to
  `needs_revision` with `outcome_source = auto_checker`, or routes passing work
  to `review_pending`;
- `review_pending` means the submission is ready for the later WS-REV boundary.
  This chunk does not create `ReviewPacketManifest`, a review queue, reviewer
  lease, reviewer assignment, or review decision;
- artifact persistence does not add, rename, or reinterpret checker lifecycle
  outcomes;
- changed subsystem coverage is at least 90 percent and repository coverage
  remains at least 78 percent;
- backend CI installs this chunk's exact focused 90 percent gate, preserves
  every earlier scoped 90 percent gate, and retains the exact 78 percent
  repository command below; `scripts/test_agent_gates.py` fails on workflow
  command, source-set, threshold, or cumulative-retention drift;
- the stale-contract phase advances to `checker_cutover` only after both checker
  paths consume bindings and the phase scan passes.

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
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_checker_artifacts.py tests/test_post_submit_checkers.py -q --cov=app.interfaces.artifact_operations --cov=app.modules.checkers --cov=app.modules.artifacts --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Are checker outputs bound to the exact run and independently verified?
- Can infrastructure failure ever become contributor blame?
- Is the WS-REV ownership boundary preserved?
