# Chunk Contract: WS-ART-001-04B Pre-Submit Admission

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 04A

Artifact contract phase: `upload_admission`

## Goal

Execute the task's locked project pre-submit checker against one sealed
artifact set and persist an exact admission, including bounded continuation
when artifact infrastructure is temporarily unavailable.

## Allowed Files

- pre-submit attempt/admission models and one migration;
- task/checker/artifact input assembly, execution, repository, service, router,
  schemas, and stable infrastructure error mapping;
- the canonical artifact scratch manager and one authorized, bounded,
  digest-verifying checker materializer shared by both checker phases;
- artifact/task/checker call sites consuming exact decisions already delivered
  by the approved WS-AUTH dependency; no Authorization Service owner files;
- focused migration, idempotency, concurrency, outage, checker, and real-API tests;
- `.github/workflows/backend.yml` only to expand the exact 90 percent scoped gate;
- `scripts/test_agent_gates.py` only to assert that backend CI retains this
  chunk's exact scoped coverage sources and fail-closed 90 percent threshold;
- `scripts/check_stale_artifact_contracts.py` and its focused tests only to
  advance the marker to `upload_admission`;
- related docs and chunk memory.

## Not Allowed

- submission creation or consumption of an admission;
- post-submit execution or review routing;
- any storage outage translated into checker failure, `needs_revision`, reject,
  payment, contribution, or reputation state;
- Project Manager or Operator approval to continue a contributor precheck;
- client policy/checker/provider overrides.

## Acceptance Criteria

- authoritative pre-submit executes the task's locked project checker against
  the exact sealed artifact-set hash;
- checker workspace creation declares
  `artifact.pre_submit.checker_input.materialize`, mapped to the fixed service
  permission `artifact.checker_input.materialize`; contributor upload
  permissions do not authorize materialization;
- pre-submit passes a provider-neutral materialization request for the sealed
  upload artifact set and resolves only its verified `ready` items; it does not
  require or create a product binding before submission creation. Post-submit
  later uses the same materializer with immutable binding IDs;
- the shared materializer reserves its complete checker workspace in the
  canonical scratch ledger and recomputes every SHA-256 and byte count while
  reading the exact provider bytes;
- a mismatch fails closed as an artifact incident before checker execution;
  verified files are sealed read-only before the checker receives the workspace
  handle, and the handle cannot expose provider references or credentials;
- the canonical manager owns aggregate quota, private/no-follow paths, normal
  completion and cancellation cleanup, crash/stale cleanup, and fail-closed
  exhaustion for both source preparation and checker workspace allocations;
- a passing admission binds actor, task, session, artifact set, locked guide/
  policy/checker context, canonical request digest, checker result, and expiry;
- checker failure returns structured results and creates no admission,
  submission, product review decision, or contributor outcome;
- Workstream owns a bounded transient retry budget for artifact reads;
- exhausted transient storage failure returns HTTP 503 with stable code
  `pre_submission_infrastructure_unavailable`, not checker failure;
- on infrastructure unavailability the sealed session and artifact set remain
  sealed, unconsumed, and reusable until normal expiry; only infrastructure
  attempt and audit facts are persisted;
- idempotency scope includes actor, task, sealed session/artifact set, locked
  context, client key, and canonical request digest; exact replay continues or
  returns the same attempt, changed replay conflicts, and concurrent replay
  creates no duplicate admission or attempt;
- after retry-after or infrastructure recovery, the contributor can continue
  the same exact attempt without manager/operator approval;
- changed subsystem coverage is at least 90 percent and repository coverage
  remains at least 78 percent;
- backend CI installs this chunk's exact focused 90 percent gate, preserves
  every earlier scoped 90 percent gate, and retains the exact 78 percent
  repository command below; `scripts/test_agent_gates.py` fails on workflow
  command, source-set, threshold, or cumulative-retention drift;
- the stale-contract phase advances to `upload_admission` only after the sealed
  artifact admission path is active and the phase scan passes.

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
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_submission_precheck.py tests/test_artifact_precheck_outage.py tests/test_checker_materialization.py tests/test_artifact_scratch_manager.py -q --cov=app.modules.artifacts --cov=app.modules.tasks --cov=app.modules.checkers --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Is the exact staged payload bound to one admission?
- Can infrastructure failure ever become contributor blame or product state?
- Are retry and idempotency semantics exact under concurrency and replay?
- Does pre-submit execute only the read-only bytes whose digest and size it
  recomputed through the shared materializer?
