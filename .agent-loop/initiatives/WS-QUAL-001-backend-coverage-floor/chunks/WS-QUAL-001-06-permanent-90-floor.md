# Chunk Contract: WS-QUAL-001-06 Permanent 90 Percent Floor

## Goal, risk, and budget

Close residual gaps limited to auth adapters/dependencies, project-agent
adapter, app lifespan, actors, queue wrappers, schemas, and workers. Risk L1,
SLA P1, at most 500 changed lines, permanent floor at least 90.000000 percent.

## Allowed files

```text
backend/tests/test_actors.py
backend/tests/test_agent_runtime.py
backend/tests/test_app.py
backend/tests/test_auth.py
backend/tests/test_config.py
backend/tests/test_db_session.py
backend/pyproject.toml
.github/workflows/backend.yml
docs/operations_backend_testing.md
.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

Production/app/migration changes, other test files, new fixture modules, test
weakening/deletion, skips/xfail, coverage exclusions/pragmas, or more than 500
changed lines.

## Acceptance criteria

- Additive tests close only residual missing behaviors in the enumerated module
  groups and assert return/state/error/redaction/lifespan outcomes.
- Exact reviewed tree passes isolated full coverage at 90.000000% or above;
  configured `fail_under` and CI command are at least 90 and cannot regress.
- Coverage inventory/policy, Ruff, docstring coverage, `pip check`, API contract
  drill on the isolated strict-name DB, stale wording, and Markdown links pass.
- Runbook contains final commands, safe credentials, cleanup, ratchet history,
  troubleshooting, and no ordinary use of the write-risk override.

## Verification

```bash
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py -- .venv/bin/python -m pytest -q tests/test_actors.py tests/test_agent_runtime.py tests/test_app.py tests/test_auth.py tests/test_config.py tests/test_db_session.py)
(cd backend && .venv/bin/python -m ruff check tests scripts)
(cd backend && .venv/bin/docstr-coverage --config .docstr.yaml)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py -- .venv/bin/python -m pytest -q --cov=app --cov-report=term-missing --cov-report=json:coverage.json)
(cd backend && .venv/bin/python scripts/coverage_policy.py --coverage-json coverage.json --base-ref origin/main --minimum-milestone=90 --max-implementation-lines=500 --check-test-delta)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-dsn> .venv/bin/python scripts/run_isolated_tests.py -- .venv/bin/python scripts/api_contract_e2e.py)
(cd backend && .venv/bin/python -m pip check)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Reviewers and human focus

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta. Human focus: real residual behavior,
no exclusions, exact 90% proof, API drill isolation, and permanent CI command.

## Stop

Stop after the trust bundle and merge. Update and merge final initiative status,
evidence, loop state, queue, and review log before closing WS-QUAL-001. AUTH-02
may resume only after that memory completes and the user explicitly starts it.
