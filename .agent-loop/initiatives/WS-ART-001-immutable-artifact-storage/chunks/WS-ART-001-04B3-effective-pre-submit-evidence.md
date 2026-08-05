# Chunk Contract: WS-ART-001-04B3 - Effective Pre-Submit Evidence

Initiative: `WS-ART-001` | Risk: L1 | Status: Active after merged PR #282

Artifact contract phase: `upload_admission`

## Goal

Execute the exact task-locked Project Guide rules through the same 04B1 plan and
04B2 sealed workspace, then persist one bounded immutable evidence set for the
complete platform-plus-project execution. Create no provider object, admission,
Submission, or separate contributor route.

## Allowed Files

- `backend/app/modules/checkers/pre_submit_execution.py` and new narrowly named
  pre-submit result/primitive modules under `backend/app/modules/checkers/`;
- the narrow `backend/app/modules/checkers/compiler.py` projection that binds a
  locked required-artifact/evidence key to its server-approved canonical ZIP
  path; it may not change the policy schema, catalogue, or compilation authority;
- new pre-submit evidence models/repository under
  `backend/app/modules/artifacts/`, plus their schema exports;
- the narrow actor/task model constraints required to make evidence
  actor-identity-assignment-task-project lineage database-enforced;
- one Alembic migration for the closed pre-submit evidence schema;
- the smallest task-context assembler needed to lock/reload task, assignment,
  predecessor, guide and policy lineage before persistence;
- `backend/tests/test_effective_pre_submit_execution.py`,
  `backend/tests/test_submission_precheck_scratch.py`, migration tests, semantic
  lane ownership, docs, review evidence, and exact CI-gate assertions.

## Not Allowed

- project executable code, arbitrary shell/network access, or agent judgment;
- a second project checker API/registry or caller-selected checker names;
- `pre_submit_static_feedback`, `CheckerRegistry`, `SubmissionCreate`, legacy
  package URI/evidence-item inputs, or any other caller-owned precheck path;
- reuse of post-submit `CheckerRun`/`CheckerResult`, creation of a fake or early
  Submission, or changes to the post-submit checker repository lifecycle;
- provider I/O, verified admission, Submission, Review, contribution, payment,
  reputation, post-submit routing, or AUTH activation/grant changes;
- filenames, scratch/provider references, credentials, raw checker output, or
  unbounded details in durable evidence.

## Persistence And Orchestration Lock

- `PreSubmitEvidenceSet` owns the immutable attempt context; normalized
  `PreSubmitEvidenceResult` rows own the ordered result members. Required
  provenance is held in typed columns, never generic JSON metadata.
- One deterministic operation identity binds actor, task, project, assignment,
  predecessor selector, prepared generation, archive digest/size, manifest ID
  and hash, effective-plan hash, catalogue manifest hash, and locked guide,
  artifact-policy, and checker-policy hashes.
- A database uniqueness constraint permits exactly one evidence set for that
  operation identity. Exact replay returns the same set; any reused operation
  identity with different bound facts fails closed as a conflict.
- The sealed-tree callback executes both phase families and returns one bounded
  canonical result DTO. A separate transaction-bound orchestration/repository
  boundary persists it only after locked context revalidation; scratch and
  materialization services never perform evidence writes.
- The durable evidence set is audit/provenance. The successful immediate-use
  capability remains process-local, single-use, and generation/predecessor
  bound for 04C; an evidence-set ID alone is never a consumption capability.

## Acceptance Criteria

- one ordered result contains both platform/default and locked project entries,
  each with stable catalogue definition ID/version, source, status, severity,
  bounded code/message,
  and policy trace;
- 04B2 results and project-policy results are normalized into that one envelope
  before persistence; no parallel default/project result contract survives;
- the canonical typed result envelope nests identity under `definition`
  (`dispatch_authority`, authority-neutral definition ID/version, public name,
  source) and trace
  under `policy_trace` (effective-plan hash, deterministic rule-instance ID,
  locked-policy hash); immutable evidence persists each member explicitly and
  never relies on open-ended `metadata` for required provenance; for this
  pre-submit authority, definition ID/version are exactly the stable catalogue
  definition ID/version; the effective plan separately binds the top-level
  catalogue ID/version and manifest hash;
- execution binds actor/task/project/assignment, predecessor, archive identity,
  manifest ID/hash, scratch generation, locked guide/policy/checker hashes, and
  effective plan identity;
- project rules consume server-derived manifest/workspace facts and may require
  project-specific files such as `task.toml` without making them platform defaults;
- locked policy keys resolve through one closed server-owned key-to-canonical-path
  projection; unknown, duplicate or unmappable keys are retryable policy/setup
  failures, and contributor labels or evidence tokens cannot satisfy them;
- project policy can add/narrow but cannot disable, reorder, downgrade, or raise
  platform limits;
- blocking pre-submit checker results create no durable artifact, admission, Submission, review,
  contribution, compensation, reputation, or provider charge;
- infrastructure/authorization failure is retryable platform state, never
  contributor blame or a product review decision;
- the passing result is short-lived, single-use, and bound to the same scratch
  generation/predecessor for immediate 04C consumption;
- crossed-state tests prove stale/replaced predecessor, closed task, changed or
  revoked assignment/authority, locked-context change, and scratch-generation
  mismatch invalidate the result at the immediate-consumption boundary and
  create no artifact, provider write, admission, Submission, or lifecycle effect;
- no ID-addressed evidence-read route or independently invocable precheck route
  is introduced; the eventual 04C2 endpoint returns only bounded same-request
  results;
- the only audit projection is `pre_submission_check_failed` with bounded
  attempt/result identifiers, stable codes, counts and categories; it excludes
  filenames, paths, scratch/provider references, credentials, raw output,
  evidence content, free-form checker messages and review-finding vocabulary;
- focused subsystem coverage is at least 90 percent and repository coverage
  remains at least 78 percent.

## Verification

```bash
docker compose up -d --wait postgres redis
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_effective_pre_submit_execution.py tests/test_default_pre_submit_execution.py -q)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/coverage report --include='app/modules/artifacts/*,app/modules/checkers/*,app/modules/tasks/*' --precision=2 --fail-under=90)
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py
```

## Exact CI Coverage Gates

The hosted Backend Gates retain every existing ART/checker coverage report.
This chunk must additionally prove or preserve exactly:

```bash
coverage report --include='app/modules/artifacts/*' --precision=2 --fail-under=90
coverage report --include='app/modules/checkers/*' --precision=2 --fail-under=90
coverage report --include='app/modules/tasks/*' --precision=2 --fail-under=90
coverage report --include='app/modules/audit/*' --precision=2 --fail-under=90
coverage report --include='app/api/router.py' --precision=2 --fail-under=90
coverage report --include='app/main.py' --precision=2 --fail-under=90
```

If implementation does not change one of those surfaces, its existing hosted
gate remains unchanged; it may not be removed or weakened.

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Is there exactly one execution and evidence chain?
- Can locked project rules observe anything other than the exact sealed bundle?
- Are checker findings kept separate from review decisions and lifecycle state?
