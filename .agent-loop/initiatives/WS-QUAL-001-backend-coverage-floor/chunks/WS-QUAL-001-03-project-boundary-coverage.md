# Chunk Contract: WS-QUAL-001-03 Project Boundary Coverage

## Goal, risk, and budget

Cover project repository and router success/error mappings not reached by chunk
02. Risk L1, SLA P1, at most 500 changed lines, exit floor at least 84.000000%.

## Allowed files

```text
backend/tests/test_projects.py
backend/pyproject.toml
.github/workflows/backend.yml
.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

`backend/app/**`, `backend/alembic/**`, other tests, new fixture modules, API or
schema changes, test weakening/deletion, skips/xfail, coverage exclusions or
pragmas, or more than 500 changed lines.

## Acceptance criteria

- Additive tests cover repository missing/conflict/stale/update paths and router
  401/403/404/409/503 mappings identified by the current missing-line report.
- Assertions prove HTTP body/status and persisted or unchanged state.
- Existing fixtures/clients are reused without copied setup.
- Full coverage and configured floor reach at least 84.000000% under the exact
  non-decreasing evidence formula.

## Verification

```bash
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py -- .venv/bin/python -m pytest -q tests/test_projects.py)
(cd backend && .venv/bin/python -m ruff check tests/test_projects.py)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py -- .venv/bin/python -m pytest -q --cov=app --cov-report=json:coverage.json)
(cd backend && .venv/bin/python scripts/coverage_policy.py --coverage-json coverage.json --base-ref origin/main --minimum-milestone=84 --max-implementation-lines=500 --check-test-delta)
(cd backend && .venv/bin/python -m pip check)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Reviewers and human focus

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, reuse/dedup, and test delta. Human focus: mapped boundary behavior,
state assertions, delta integrity, size budget, and 84% proof.

## Stop

Stop and replan if the floor or size budget is missed. After merge, update and
merge initiative status/evidence plus global loop state, queue, and review log.
Do not start chunk 04 until that memory completes and the user starts it.
