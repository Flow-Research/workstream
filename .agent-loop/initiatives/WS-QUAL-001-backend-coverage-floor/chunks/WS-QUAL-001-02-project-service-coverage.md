# Chunk Contract: WS-QUAL-001-02 Project Service Coverage

## Goal, risk, and budget

Cover project setup, policy derivation/approval/correction, audit, queue, and
recovery service behavior. Risk L1, SLA P1, at most 500 changed lines, exit floor
at least 82.000000 percent.

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

`backend/app/**`, migrations, API/schema changes, new duplicate fixture modules,
test deletion/skips/xfail, assertion weakening, coverage exclusions/pragmas, or
more than 500 changed lines.

## Acceptance criteria

- Additive tests cover setup continuation, derivation, approval/correction,
  queue failure/recovery, audit, provenance, stale/current policy, and role
  rejection outcomes exposed by the missing-line report.
- Assertions prove returned/persisted/audit/queue/fail-closed outcomes.
- Tests reuse existing project fixtures; no copied DB reset or actor/client
  factory.
- Full coverage is at least 82.000000 percent and the configured floor becomes
  `max(previous_merged_floor, measured_six_decimal_percent)` without regression.
- Evidence inventories all added/modified/deleted/skipped tests; deletions and
  skips require explicit rejection evidence and are otherwise forbidden.

## Verification

```bash
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py -- .venv/bin/python -m pytest -q tests/test_projects.py)
(cd backend && .venv/bin/python -m ruff check tests/test_projects.py)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py -- .venv/bin/python -m pytest -q --cov=app --cov-report=json:coverage.json)
(cd backend && .venv/bin/python scripts/coverage_policy.py --coverage-json coverage.json --base-ref origin/main --minimum-milestone=82 --max-implementation-lines=500 --check-test-delta)
(cd backend && .venv/bin/python -m pip check)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Reviewers and human focus

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, reuse/dedup, and test delta. Human review focuses on real project
outcomes, fixture reuse, additive assertions, 500-line budget, and 82% proof.

## Stop

Stop and replan if the floor or size budget is missed. After merge, update and
merge initiative status/evidence plus global loop state, queue, and review log.
Do not start chunk 03 until that memory completes and the user starts it.
