# Chunk Contract: WS-CON-001-08R - Bound-Service Callback Rate Control

## Goal and risk

Extend the shared closed API-control service with one durable actor+binding
callback scope before the external fulfillment route exists. L1 abuse-control/
availability/data risk.

## Allowed files

```text
backend/app/modules/api_controls/{models,repository,service}.py
backend/app/api/deps/api_controls.py
backend/app/core/config.py
backend/alembic/versions/<next>_compensation_callback_rate_scope.py
backend/tests/{test_api_rate_controls,test_config,test_alembic}.py
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-08R.json
```

## Not allowed

```text
AUTH catalogue/grant/kernel/service-actor edits
callback route/receipt/award/binding behavior
in-memory/shared-IP-only limiter, new rate-control framework, dependency/CI weakening
```

## Acceptance criteria

- [ ] Closed scope adds only `compensation_fulfillment_report`; key digest is
  derived from canonical service actor + binding and stores neither raw secret
  nor provider credential/reference.
- [ ] Bounded configuration, PostgreSQL atomic window accounting, fail-closed
  storage errors and deterministic retry-after behavior reuse RateControlService.
- [ ] Actor A cannot exhaust actor B; binding A cannot bypass binding B; exact
  boundary/concurrency/upgrade/downgrade behavior is tested.
- [ ] No callback or authorization decision is implemented in this chunk.

## Verification and reviewers

Execute the exact clean isolated CON-08R row in `../RUNTIME_VERIFICATION.md`,
replace its migration placeholder with the one new revision, then run:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_api_rate_controls.py tests/test_config.py tests/test_alembic.py -k '(compensation_fulfillment_report or rate) and (atomic or window or concurrent or isolation or upgrade or downgrade or fail_closed or retry_after)')
(cd backend && .venv/bin/python -m coverage report --include='app/modules/api_controls/*' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/api/deps/api_controls.py' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/core/config.py' --fail-under=90)
```

Pass requires a non-empty selected test set, atomic PostgreSQL window races,
actor and binding isolation, upgrade/downgrade proof, bounded configuration,
fail-closed storage errors, deterministic retry-after, repository coverage at
least 78 percent in the same clean run, and every focused report at least 90
percent. Senior engineering, QA/test, security/auth, product/ops, architecture,
docs, reuse/dedup and test-delta are required. Stop before callback.
