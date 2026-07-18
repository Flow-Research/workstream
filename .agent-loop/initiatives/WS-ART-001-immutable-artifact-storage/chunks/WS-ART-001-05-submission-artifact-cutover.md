# Chunk Contract: WS-ART-001-05 Submission Artifact Cutover

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 04B

Artifact contract phase: `submission_cutover`

## Goal

Make submission creation atomically consume the exact passing admission and
sealed artifact set, create immutable submission bindings, and automatically
enter `evaluation_pending` without manager finalization.

## Allowed Files

- submission/task models, migration, repository, schemas, service, and router
- artifact admission consumption and binding service
- project policy/compiler and checker contract files only to remove the legacy
  caller storage-scheme, manifest/hash, and compiler-primitive fields owned by
  this clean cut
- Celery post-submit dispatch handoff
- task/artifact call sites consuming exact decisions already delivered by the
  approved WS-AUTH dependency; no Authorization Service owner files
- focused migration, race, API, and real-flow tests
- `.github/workflows/backend.yml` only to expand the exact 90 percent scoped gate
- `scripts/test_agent_gates.py` only to assert the exact workflow command,
  source set, threshold, and cumulative retention
- `backend/scripts/week2_api_e2e.py` to migrate its complete upload,
  pre-submit, and submission flow from legacy transport fields and the removed
  `/finalize` route
- `backend/scripts/api_contract_e2e.py` only to migrate project-policy,
  submission request, and response assertions from legacy storage fields to
  upload-session/admission semantics
- `examples/terminal_benchmark/terminal_benchmark_api_e2e.py` only to migrate
  its private local fixture and manual API example from removed transport and
  storage-policy fields; this sanitized local example is not CI or acceptance
  proof, and Chunk 07 owns standalone executable proof
- `scripts/check_stale_artifact_contracts.py` and its focused tests only to
  advance the marker to `submission_cutover`
- related docs/chunk memory

## Not Allowed

- reviewer decision/revision implementation;
- manager/admin finalization of ordinary contributor submissions;
- caller package URI, package hash, artifact manifest, evidence IDs, provider
  reference, or artifact-set hash;
- direct provider calls from task/submission modules;
- checker-result interpretation as a human review decision.
- Authorization Service implementation, permission registration, or policy
  changes.

## Acceptance Criteria

- immutable submission binding creation declares
  `artifact.submission.binding.create`, mapped to the fixed service permission
  `artifact.binding.create`; submission creation authority does not imply it;

- request body contains only summary, contributor attestation, and upload
  session ID.
- assigned contributor can create their own submission after exact pre-submit
  admission passes; no manager action is required.
- one transaction locks and consumes admission/session/items once, allocates
  server submission version, creates immutable bindings, stamps exact locked
  policy/checker/artifact-set context, and transitions to
  `evaluation_pending`.
- the exact payload checked is the payload submitted; changed summary,
  attestation, task, actor, policy, checker, session, or artifact set fails.
- automatic post-submit dispatch is durable and duplicate-safe.
- concurrent/replayed creation yields one submission/business effect.
- the misleading `/submissions/{id}/finalize` route is replaced by the exact
  Operator-only `/operator/submissions/{id}/pre-review-gate-repair` command;
  existing API-only drill consumers move in the same clean cut.
- pre-review-gate repair requires exact authorization, reason, audit, and a
  failed/stale automatic dispatch; it cannot re-finalize healthy submissions or
  create another checker run.
- storage failure leaves infrastructure state and never blames contributor.
- no live project/task/checker contract retains the removed caller transport,
  storage-policy, or compiler-primitive fields; immutable Alembic history and
  test fixture literals are not rewritten merely to satisfy wording scans.
- changed subsystem coverage is at least 90 percent and repository coverage
  does not decrease.
- backend CI installs this chunk's exact focused 90 percent gate, preserves
  every earlier scoped 90 percent gate, and retains the exact 78 percent
  repository command below; `scripts/test_agent_gates.py` fails on workflow
  command, source-set, threshold, or cumulative-retention drift.
- the stale-contract phase advances to `submission_cutover`; active docs and
  project/task/checker contracts contain no caller-owned provider URI
  references and the phase scan passes.

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
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_submission_api.py tests/test_submission_concurrency.py tests/test_projects.py tests/test_checkers.py -q --cov=app.modules.tasks --cov=app.modules.artifacts --cov=app.modules.projects --cov=app.modules.checkers --cov=app.adapters.project_agents --cov=app.interfaces.project_agents --cov=app.workers --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week2_api_e2e.py)
(cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py)
(cd backend && .venv/bin/python -m py_compile ../examples/terminal_benchmark/terminal_benchmark_api_e2e.py)
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Does contributor intent produce and lock exactly one submission version?
- Is all manager finalization removed from the normal path?
- Is pre-submit payload binding authoritative and race-safe?
- Are all active API callers migrated without treating the private local
  Terminal Benchmark example as reproducible proof?
