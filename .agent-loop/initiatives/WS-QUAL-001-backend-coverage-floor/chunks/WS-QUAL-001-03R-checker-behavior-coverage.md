# Chunk Contract: WS-QUAL-001-03R — Checker Behavior Coverage

Parent initiative: `WS-QUAL-001`

Goal: if still necessary after 02R, add meaningful fast tests for current
checker service, repository, runner, compiler, and routing gaps.

Risk: L2 test-only; P2.

Allowed files:

- `backend/tests/test_checkers.py`
- `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/**`

Not allowed: production code, migrations, workflow/threshold changes, skips,
xfails, coverage exclusions, assertion deletion, or duplicate system flows.

Acceptance: observable outcomes, focused proof, recorded runtime impact,
complete hosted Backend, and exact global coverage of at least 90.25 percent.
If meaningful checker gaps are exhausted first, stop and plan one explicit
owner-specific successor rather than add artificial tests.

Verification commands:

- `cd backend && ruff check tests/test_checkers.py`
- `cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres python scripts/run_isolated_tests.py --metadata-json .ci/qual-03r-database.json --timeout-seconds 1200 -- pytest -q tests/test_checkers.py`
- Hosted Backend semantic lanes and final coverage fan-in.
- Test-delta scan for skips, xfails, deleted assertions, and coverage narrowing.

Required reviewers: senior, QA, test-delta, CI integrity, product/ops, reuse.
Human focus: checker invariant ownership and fast-layer placement. This chunk
does not change or test TASK-owned lifecycle behavior merely for percentage.
An unexplained focused-test or hosted-wall increase above 10 percent stops the
chunk for review; ordinary hosted-run noise must be documented.

Stop on stale evidence, production defect, or architecture expansion.
