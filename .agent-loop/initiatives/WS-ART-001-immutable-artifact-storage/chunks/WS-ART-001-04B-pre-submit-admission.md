# Chunk Contract: WS-ART-001-04B Scratch-Bound Pre-Submission Checks

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 04A

Artifact contract phase: `upload_admission`

## Goal

Run mandatory Workstream archive gates and the task's locked Project Guide
pre-submission checker against the exact prepared ZIP tree while it remains in
bounded private scratch. Persist checker evidence, but create no durable
artifact content, provider object, or Submission.

## Allowed Files

- ART/checker/task input assembly for one prepared bundle;
- the shared bounded, read-only scratch workspace/materialization capability;
- pre-submit attempt/result control-plane models and one migration;
- hidden task/checker surfaces with ART-owned canonical resource facts/guards;
- focused checker, timeout, cleanup, concurrency, API, coverage, docs, and
  chunk-memory changes;
- CI files only to add and preserve the exact scoped 90 percent gate.

## Not Allowed

- provider I/O, candidate storage, `ArtifactContent`, replica, or binding;
- passing admission publication or Submission creation;
- post-submit routing or Review/Contribution/delivery changes;
- checker interpretation as `accept`, `needs_revision`, or `reject`;
- manager/operator approval for an ordinary contributor retry;
- AUTH-owned activation changes or larger configured limits.

## Acceptance Criteria

- platform-owned format, safety, manifest, change, and scratch-integrity gates
  cannot be disabled or weakened by a Project Guide;
- the project checker uses the exact task-locked guide/policy/checker context and
  may require content such as `task.toml`, directories, evidence, configuration,
  or tests from the safely materialized outer-ZIP tree;
- project policy may narrow platform limits but cannot raise them;
- checker input records the archive commitment, manifest ID/hash, task, actor,
  locked policy context, and scratch generation used;
- durable attempt/evidence records are actor/task/attempt scoped, contain no raw
  bytes, filenames, scratch/provider references, credentials, or unbounded
  checker output, and follow the existing audit retention policy;
- v0.1 exposes no ID-addressed pre-submit-evidence read route. The authorized
  contributor receives only the bounded redacted result of the same continuous
  request; existing authorized audit/Operator surfaces may diagnose metadata,
  while reviewers, CON, and delivery cannot consume it before Submission binding;
- the checker receives a read-only private workspace and no provider reference,
  credential, mutable intake path, or arbitrary host path;
- checker workspace creation uses the distinct fixed service action
  `artifact.checker_input.materialize`; contributor preparation authority never
  grants or substitutes for that service authority;
- a checker failure creates structured findings only: no durable artifact,
  admission, Submission, Review decision, contribution, payment, reputation, or
  provider charge;
- infrastructure failure remains a stable retryable infrastructure outcome and
  never becomes contributor blame or product review state;
- successful checks create a short-lived, single-use passing result bound to the
  same scratch handle and exact predecessor observed in 04A; they do not make
  bytes authoritative or durable;
- 04B remains an internal hidden library seam with no separately invocable
  contributor route; 04C composes the one continuous same-process endpoint;
- the complete operation remains process-local through 04C; process loss or
  scratch loss invalidates the result and requires reupload rather than routing
  a later distributed worker to a local path;
- completion, failure, cancellation, deadline, and abandoned-work cleanup are
  bounded and idempotent;
- the continuous contributor surface remains hidden; this chunk does not
  activate the planned contributor action or change fixed service grants;
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
docker compose up -d --wait postgres redis
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_submission_precheck.py tests/test_submission_precheck_scratch.py tests/test_checker_materialization.py tests/test_artifact_scratch_manager.py -q --cov=app.modules.artifacts --cov=app.modules.checkers --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Can a failed or unchecked bundle reach object storage?
- Can an async/distributed worker receive an unusable local scratch path?
- Are checker findings separate from reviewer decisions?
