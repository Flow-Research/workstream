# Chunk Contract: WS-QUAL-001-05 Checker Coverage

## Goal, risk, and budget

Cover checker service, compiler, runner, repository, router, queue, and worker
behavior. Risk L1, SLA P1, at most 500 changed lines, exit floor at least
88.000000 percent.

## Allowed files

```text
backend/tests/test_checkers.py
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

Additive tests cover compilation validation, pre/post-submit execution,
repository and router failures, queue/retry/recovery, audit visibility, and
worker error redaction identified by current missing lines. Existing checker
fixtures are reused. Full coverage and configured floor reach at least
88.000000 percent.

## Verification

```bash
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py -- .venv/bin/python -m pytest -q tests/test_checkers.py)
(cd backend && .venv/bin/python -m ruff check tests/test_checkers.py)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py -- .venv/bin/python -m pytest -q --cov=app --cov-report=json:coverage.json)
(cd backend && .venv/bin/python scripts/coverage_policy.py --coverage-json coverage.json --base-ref origin/main --minimum-milestone=88 --max-implementation-lines=500 --check-test-delta)
(cd backend && .venv/bin/python -m pip check)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Reviewers and human focus

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, reuse/dedup, and test delta. Human focus: checker lifecycle and error
redaction, queue/audit assertions, delta integrity, size budget, and 88% proof.

## Stop

Stop and replan if the floor or size budget is missed. After merge, update and
merge initiative status/evidence plus global loop state, queue, and review log.
Do not start chunk 06 until that memory completes and the user starts it.
