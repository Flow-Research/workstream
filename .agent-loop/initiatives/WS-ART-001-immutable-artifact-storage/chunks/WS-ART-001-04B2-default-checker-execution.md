# Chunk Contract: WS-ART-001-04B2 - Default Checker Execution

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 04B1

Artifact contract phase: `upload_admission`

## Goal

Project the already inspected outer ZIP into one sealed read-only scratch tree
and execute the mandatory artifact-custody and Workstream-default phases of the
04B1 plan against exact server-derived facts. Do not execute project-specific
rules or persist the final evidence set yet.

## Allowed Files

- shared checker-input materialization through `ArtifactScratchManager`;
- execution adapters for catalogue entries backed by 04A2/04A3 capabilities;
- platform/default phase orchestration, bounded result types, cleanup and tests;
- fixed-service materializer resource facts/guards while the action remains
  planned and unavailable;
- focused docs, evidence, and CI gate maintenance.

## Not Allowed

- re-parsing through a second ZIP implementation or changing 04A identities;
- arbitrary execution, network access, direct temp paths, or provider I/O;
- project-specific rule execution or durable evidence/admission/Submission;
- passing scratch paths or prepared handles across processes or Celery;
- AUTH activation/grants, public routes, post-submit/review/contribution work.

## Acceptance Criteria

- one sealed materialization is derived from the 04A manifest and generation;
- archive and projected file hashes/sizes/types/executable flags agree before a
  checker can read the tree;
- fixed canonical read-only/read-execute/read-traverse modes are used and the
  executable flag never grants execution;
- mandatory catalogue unavailability, authorization denial, integrity drift,
  cancellation, timeout, or scratch exhaustion fails before checker access and
  creates no durable/provider effect;
- platform/default entries execute in deterministic dependency order and emit
  bounded path-redacted results carrying entry ID/version and plan identity;
- disabled advisory entries are explicit; disabled mandatory entries fail
  closed and cannot appear as passing or skipped-success;
- cleanup is bounded and idempotent on every terminal path;
- tests prove pre-submit and post-submit projection parity for Unix executable,
  non-Unix/invalid mode, symlink/special rejection, and permission-only revision
  cases; neither projection preserves arbitrary archive modes;
- the behavior remains hidden and process-local for later 04B3/04C composition;
- focused subsystem coverage is at least 90 percent and repository coverage
  remains at least 78 percent.

## Verification

```bash
(cd backend && .venv/bin/pytest tests/test_checker_materialization.py tests/test_default_pre_submit_execution.py tests/test_artifact_scratch_manager.py tests/test_submission_archive.py tests/test_submission_manifest.py tests/test_submission_change_gate.py -q)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/coverage report --include='app/modules/artifacts/*,app/modules/checkers/*' --precision=2 --fail-under=90)
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
coverage report --include='app/core/cancellation.py,app/core/file_locks.py' --precision=2 --fail-under=90
coverage report --include='app/interfaces/artifact_operations.py,app/interfaces/artifacts.py' --precision=2 --fail-under=90
```

If implementation does not change one of those surfaces, its existing hosted
gate remains unchanged; it may not be removed or weakened.

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Is the checked tree exactly the 04A manifest tree?
- Can any disabled/failed mandatory default be bypassed?
- Are all scratch and authorization capabilities process-local and bounded?
