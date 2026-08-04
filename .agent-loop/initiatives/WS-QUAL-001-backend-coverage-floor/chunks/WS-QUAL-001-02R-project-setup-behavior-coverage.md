# Chunk Contract: WS-QUAL-001-02R — Project And Setup Behavior Coverage

Parent initiative: `WS-QUAL-001`

Goal: add meaningful fast tests for current project/setup service, repository,
router, queue, and replay gaps selected from the refreshed hosted report.

Risk: L2 test-only; P2.

Allowed files:

- `backend/tests/test_projects.py`
- `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/**`

Not allowed: production code, migrations, workflow/threshold changes, skips,
xfails, coverage exclusions, assertion deletion, or duplicated broad HTTP flows.

Acceptance: every test asserts an observable behavior; focused tests pass;
runtime impact is recorded; complete hosted Backend passes; global coverage is
at least 89.55 percent without weakening any protected floor. If meaningful
project/setup gaps are exhausted before that target, stop and replan rather
than add artificial tests.

Verification commands:

- `cd backend && ruff check tests/test_projects.py`
- `cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres python scripts/run_isolated_tests.py --metadata-json .ci/qual-02r-database.json --timeout-seconds 1200 -- pytest -q tests/test_projects.py`
- Hosted Backend semantic lanes and final coverage fan-in.
- Test-delta scan for skips, xfails, deleted assertions, and coverage narrowing.

Required reviewers: senior, QA, test-delta, CI integrity, product/ops, reuse.
Human focus: test value and avoidance of unnecessary PostgreSQL/HTTP cost. An
unexplained focused-test or hosted-wall increase above 10 percent stops the
chunk for review; ordinary hosted-run noise must be documented.

Stop if current missing-line evidence is stale, a production defect is found,
or meaningful tests require production architecture changes.
