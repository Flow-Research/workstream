# Discovery: WS-QUAL-001 Current-Main Coverage Closure

## Audited baseline

Hosted Backend run `30835801412` on the PR #259 exact tested tree produced:

- 2,914 collected and completed tests;
- 20,787 covered statements of 23,368;
- 2,581 missed statements;
- 88.954981 percent global statement coverage;
- 936.775 seconds total backend wall time;
- 755.531 seconds in the slowest semantic lane.

At the current denominator, 90 percent permits at most 2,336 missed statements.
The suite therefore needs 245 additional covered statements, plus reasonable
headroom for concurrent application growth before the floor changes.

## Current CI behavior

`.github/workflows/backend.yml` runs five semantic lanes, combines exactly five
coverage files, runs the real API contract drill, blocks below 78 percent
globally, and applies multiple 90-percent subsystem/per-file checks. Lane
custody, PostgreSQL isolation, and coverage fan-in are already implemented.

`backend/scripts/coverage_policy.py` and
`backend/tests/test_coverage_contract.py` are merged historical integrity
machinery. The current workflow does not invoke that policy script. PLAN2 does
not wire it into CI or expand its static Python analysis.

## Largest current gaps

The latest hosted coverage JSON identifies these high-value gaps:

| Module | Statements | Missing | Coverage |
|---|---:|---:|---:|
| `app/modules/projects/service.py` | 1,527 | 520 | 65.95% |
| `app/modules/checkers/service.py` | 579 | 170 | 70.64% |
| `app/modules/authorization/router.py` | 484 | 168 | 65.29% |
| `app/modules/artifacts/service.py` | 959 | 139 | 85.51% |
| `app/modules/tasks/service.py` | 682 | 108 | 84.16% |
| `app/modules/projects/repository.py` | 282 | 87 | 69.15% |
| `app/modules/artifacts/operator.py` | 204 | 80 | 60.78% |
| `app/modules/projects/router.py` | 184 | 68 | 63.04% |
| `app/modules/artifacts/guide_extraction_worker.py` | 237 | 65 | 72.57% |

Smaller gaps exist in checker repository/router/runner/compiler, project setup
queue and policy replay, authorization read/repository code, auth API/deps/
schemas, artifact extraction/materialization, workers, and actor services.

## Existing ownership and test layers

- Project behavior: `backend/tests/test_projects.py` and focused project files.
- Task behavior: `backend/tests/test_tasks.py`.
- Checker behavior: `backend/tests/test_checkers.py` and runner tests.
- Artifact behavior: focused artifact, storage, guide, and recovery tests.
- Authorization behavior: focused actor/authorization/API tests.
- Test isolation: `backend/scripts/run_isolated_tests.py`.
- Semantic execution: `backend/scripts/run_test_lanes.py`.

The largest services depend directly on `AsyncSession`; this makes broad unit
extraction an architectural concern outside QUAL. Tests may use small typed
fakes or existing fixtures where behavior is observable, but QUAL must not
refactor production services merely to raise coverage.

## Risks discovered

- Adding another 245 database-heavy lines of coverage could worsen the current
  15.6-minute hosted wall time.
- Testing implementation branches without outcomes can manufacture percentage
  while adding little confidence.
- Raising the floor in the same PR as broad tests makes failures harder to
  diagnose and encourages threshold bargaining.
- Concurrent AUTH, ART, and REV work can increase the denominator; the final
  floor chunk must remeasure current `main` and retain headroom.

## Conventions to preserve

- Complete `backend/app` inventory and combined semantic-lane coverage.
- Real PostgreSQL for constraints, locks, migrations, transactions, triggers,
  and concurrency.
- Real MinIO for the protocol boundary.
- Global 78-percent floor until the exact 90-percent switch merges.
- Existing protected 90-percent subsystem gates.
- Test-delta and CI-integrity review for every QUAL implementation PR.

## Unknowns resolved per implementation chunk

The exact missing lines and best observable tests must be refreshed from the
then-current hosted coverage JSON. A contract may not promise a coverage gain
from stale line numbers or require tests that merely execute code.
