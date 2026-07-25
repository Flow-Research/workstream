# Chunk Contract: WS-ART-001-05 - Submission Bundle Binding Cutover

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 04C and exact AUTH activation

Artifact contract phase: `submission_cutover`

## Goal

Atomically consume one verified submission-bundle admission, create the next
immutable `Submission` row and exact artifact binding, and remove caller-owned
package transport/hash/manifest authority.

## Allowed Files

- task/submission models, migration, repository, schemas, service, and router;
- ART admission consumption and binding capability;
- project/checker contracts only for the exact legacy transport-field cutover;
- post-submit dispatch handoff and affected real-API examples;
- `backend/scripts/api_contract_e2e.py` only to migrate the exact submission
  request/response flow to verified submission-bundle admission;
- focused migration, concurrency, history, API, coverage, docs, and chunk memory;
- CI files only to add and preserve the exact scoped 90 percent gate.

## Not Allowed

- a competing `SubmissionVersion` table or alias;
- reviewer decision/note implementation, reviewer-uploaded revision files, or
  Review/Contribution/delivery ownership;
- caller package URI/hash/manifest/evidence IDs, provider references, content
  IDs, or artifact-set hashes;
- direct provider calls from task/submission modules;
- AUTH-owned activation changes or checker results interpreted as review.

## Acceptance Criteria

- one `Submission` row is one immutable version and binds exactly one verified
  outer ZIP plus its canonical semantic manifest and checker evidence;
- request body contains only contributor-authored product fields and the
  opaque verified admission identifier; all artifact identity is server-owned;
- before revealing admission state/context, the route obtains a fresh human
  authorization decision; AUTH denial remains concealed from unrelated actors;
- one transaction consumes fresh prepared human `submission.create` and fixed
  service ActionId `artifact.submission.binding.create` capabilities (mapped to
  PermissionId `artifact.binding.create`), locks task, assignment, admission and
  predecessor, and recomposes final resource facts through typed capabilities;
  ART and TASK never import AUTH-owned repositories;
- the transaction requires `ready`, matches actor profile, task, project,
  assignment, predecessor and exact locked context, allocates the next version,
  creates the immutable Submission and binding, and changes admission to
  `consumed` before one commit;
- the admission records preparation identity-link provenance, while consumption
  records its new decision/identity evidence and requires the same canonical
  actor rather than an obsolete identity-link row;
- database status/terminal-field checks and a unique Submission admission
  reference guarantee at most one consumer; `consumed` and `stale` are terminal;
- proven task closure, predecessor advancement, or locked-context replacement
  changes a still-ready admission to `stale`; authority loss alone does not, so
  restored authority may later consume a still-compatible ready admission;
- binding creation uses fixed-service ActionId
  `artifact.submission.binding.create`, mapped to PermissionId
  `artifact.binding.create`; the contributor's active
  `artifact.submission_bundle.prepare` ActionId and `submission.create`
  permission do not imply internal binding authority;
- version `N+1` records `supersedes_submission_id = N`; the exact relationship
  to a `needs_revision` Review is added only through the reviewed REV/TASK joint
  contract and cannot be fabricated from a note or client ID;
- exact replay/concurrency creates one Submission and one business effect;
- concurrent consumption yields one success and one exact replay or stable
  conflict; cancellation, denial, service-action unavailability, context drift,
  stale execution, or persistence failure creates no Submission/binding;
- after successful authorization, proven task closure, predecessor advancement,
  or locked-context replacement may commit only the terminal stale transition
  and bounded evidence; every other failed mutation rolls back authorization
  evidence and admission transition together;
- stable authorized outcomes distinguish already-consumed, context-changed, and
  stale admissions, but unauthorized callers learn no admission existence/state;
- crossed-state tests cover authority restoration for a compatible ready
  admission, predecessor advancement to stale, disabled binding service action,
  token-valid but revoked identity/grant/assignment, stale execution, and two
  concurrent requests producing one business effect;
- latest/current/accepted access uses indexed repository queries or projections,
  while the immutable version/review graph remains fully queryable;
- no manager finalization is required for an ordinary passing contributor
  submission, and infrastructure failure never blames the contributor;
- all active callers and docs lose legacy package URI, caller hash, and caller
  artifact-manifest authority without fabricated backfill for historical rows;
- migration explicitly preserves readable historical rows, refuses any unsafe
  authoritative backfill, and documents rollback/cutover ordering;
- hidden behavior remains unavailable until AUTH activates its exact actions;
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
docker compose up -d --wait postgres redis minio
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_submission_api.py tests/test_submission_concurrency.py tests/test_submission_history.py tests/test_projects.py tests/test_checkers.py -q --cov=app.modules.tasks --cov=app.modules.artifacts --cov=app.modules.projects --cov=app.modules.checkers --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py)
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Does exactly one checked and verified ZIP become exactly one Submission?
- Is the current `Submission` aggregate preserved without a duplicate model?
- Is historical migration honest and fail closed?
