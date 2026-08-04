# Chunk Contract: WS-ART-001-04B3 - Effective Pre-Submit Evidence

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 04B2

Artifact contract phase: `upload_admission`

## Goal

Execute the exact task-locked Project Guide rules through the same 04B1 plan and
04B2 sealed workspace, then persist one bounded immutable evidence set for the
complete platform-plus-project execution. Create no provider object, admission,
Submission, or separate contributor route.

## Allowed Files

- locked task/guide/effective-policy/checker context assembly;
- constrained project-rule execution through the central catalogue;
- pre-submit attempt/result/evidence control-plane models and one migration;
- bounded same-request contributor response projection and audit metadata;
- focused tests, docs, evidence, and CI gate maintenance.

## Not Allowed

- project executable code, arbitrary shell/network access, or agent judgment;
- a second project checker API/registry or caller-selected checker names;
- provider I/O, verified admission, Submission, Review, contribution, payment,
  reputation, post-submit routing, or AUTH activation/grant changes;
- filenames, scratch/provider references, credentials, raw checker output, or
  unbounded details in durable evidence.

## Acceptance Criteria

- one ordered result contains both platform/default and locked project entries,
  each with catalogue ID/version, source, status, severity, bounded code/message,
  and policy trace;
- the canonical typed result envelope nests identity under `definition`
  (`dispatch_authority`, authority-neutral definition ID/version, public name,
  source) and trace
  under `policy_trace` (effective-plan hash, deterministic rule-instance ID,
  locked-policy hash); immutable evidence persists each member explicitly and
  never relies on open-ended `metadata` for required provenance; for this
  pre-submit authority, definition ID/version are exactly catalogue ID/version;
- execution binds actor/task/project/assignment, predecessor, archive identity,
  manifest ID/hash, scratch generation, locked guide/policy/checker hashes, and
  effective plan identity;
- project rules consume server-derived manifest/workspace facts and may require
  project-specific files such as `task.toml` without making them platform defaults;
- project policy can add/narrow but cannot disable, reorder, downgrade, or raise
  platform limits;
- blocking findings create no durable artifact, admission, Submission, review,
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
- focused subsystem coverage is at least 90 percent and repository coverage
  remains at least 78 percent.

## Verification

```bash
docker compose up -d --wait postgres redis
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_effective_pre_submit_execution.py tests/test_submission_precheck_scratch.py -q)
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
