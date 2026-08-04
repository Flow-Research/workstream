# Chunk Contract: WS-QUAL-001-03R — Checker Behavior Coverage

Parent initiative: `WS-QUAL-001`

Goal: if still necessary after 02R, add meaningful fast tests for current
checker service, repository, runner, compiler, and routing gaps.

Current-main basis: Backend run `30921410531` on merge commit `5b853d50`
completed 3,068 tests with 21,453 / 23,938 covered statements (89.619016
percent), 727.166 seconds hosted wall time, and a 567.994-second slowest lane.
The 90.25-percent target requires 21,605 covered statements, a net gain of 152
on this exact denominator.

Risk: L2 test-only; P2.

Allowed files:

- `backend/tests/test_checkers.py`
- `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/**`

Not allowed: production code, migrations, workflow/threshold changes, skips,
xfails, coverage exclusions, assertion deletion, or duplicate system flows.

Acceptance: observable outcomes, focused proof, recorded runtime impact,
complete hosted Backend, and exact global coverage of at least 90.25 percent
(21,605 / 23,938 on the starting denominator).
If meaningful checker gaps are exhausted first, stop and plan one explicit
owner-specific successor rather than add artificial tests.

Verification commands:

- `cd backend && ruff check tests/test_checkers.py`
- `cd backend && qual_tmp=$(mktemp -d /tmp/ws-qual-03r-db.XXXXXX) && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$qual_tmp/metadata.json" --timeout-seconds 1200 -- .venv/bin/pytest -q tests/test_checkers.py`
- Hosted Backend semantic lanes and final coverage fan-in.
- Test-delta scan for skips, xfails, deleted assertions, and coverage narrowing.

The 1,200-second local full-file timeout is a bounded diagnostic limit on the
constrained development machine and may be reached before collection completes.
Only the hosted Backend exact-head run is authoritative proof of the complete
suite pass.

Required reviewers: senior, QA, test-delta, CI integrity, product/ops, reuse.
Human focus: checker invariant ownership and fast-layer placement. This chunk
does not change or test TASK-owned lifecycle behavior merely for percentage.
An unexplained focused-test or hosted-wall increase above 10 percent stops the
chunk for review; ordinary hosted-run noise must be documented.

Stop on stale evidence, production defect, or architecture expansion.
