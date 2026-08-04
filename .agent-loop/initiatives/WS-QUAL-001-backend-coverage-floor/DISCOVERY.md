# Discovery: WS-QUAL-001 Current-Main Coverage Closure

## Audited baseline

### Current-main refresh for 03R

Backend run `30915102589` on current-main merge commit `cda59fc3` completed
3,056 tests, covered 21,348 of 23,826 statements (89.599597 percent), recorded
846.531 seconds total hosted wall time, and a 659.823-second slowest lane.
Reaching 90.25 percent on this denominator requires 21,503 covered statements,
a net gain of 155. The focused 03R test union covers 168 statements missing
from this hosted report: checker service 107, runner 45, and compiler 16. That
projects 21,516 / 23,826, or 90.304709 percent; hosted exact-head fan-in remains
authoritative.

Checker-owned gaps are sufficient and remain unchanged by ART: service 169,
runner 45, compiler 26, router 12, repository 11, gate queue 2, and pre-review
gate 1. Existing checker tests are integration-heavy. Direct fast coverage is
still missing for observable policy-shape rejection, registry ordering and
conflicts, routing priority, blocking-policy escalation, role-sensitive result
redaction, and bounded gate recovery outcomes. These are the preferred 03R
test seams; unrelated TASK or ART lifecycle paths remain out of scope.

### PLAN2 historical baseline

Hosted Backend run `30854931616` on the final PR #249 tested tree
`19d48f7ea4bf20cb29f03cbba54f98683ce52661` produced:

- 2,925 collected and completed tests;
- 20,793 covered statements of 23,475;
- 2,682 missed statements;
- 88.575080 percent global statement coverage;
- 640.284 seconds total backend wall time;
- 468.506 seconds in the slowest semantic lane.

At the current denominator, 90 percent permits at most 2,347 missed statements.
The suite therefore needs 335 additional covered statements to reach 90
percent and 394 to reach the required 90.25-percent pre-switch headroom.

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
| `app/modules/projects/service.py` | 1,451 | 550 | 62.10% |
| `app/modules/checkers/service.py` | 579 | 169 | 70.81% |
| `app/modules/authorization/router.py` | 484 | 168 | 65.29% |
| `app/modules/artifacts/service.py` | 959 | 138 | 85.61% |
| `app/modules/tasks/service.py` | 682 | 108 | 84.16% |
| `app/modules/projects/repository.py` | 285 | 96 | 66.32% |
| `app/modules/artifacts/operator.py` | 204 | 80 | 60.78% |
| `app/modules/projects/router.py` | 178 | 63 | 64.61% |
| `app/modules/artifacts/guide_extraction_worker.py` | 237 | 65 | 72.57% |

Smaller gaps exist in checker repository/router/runner/compiler, project setup
queue and policy replay, authorization read/repository code, auth API/deps/
schemas, artifact extraction/materialization, background-job modules, and actor
services.

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

- Adding hundreds of database-heavy covered lines could worsen the current
  10.7-minute hosted wall time.
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
