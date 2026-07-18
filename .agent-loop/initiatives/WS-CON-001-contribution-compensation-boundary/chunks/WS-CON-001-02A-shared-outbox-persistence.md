# Chunk Contract: WS-CON-001-02A - Shared Transactional Outbox Persistence

## Goal and risk

Land feature-neutral PostgreSQL outbox truth and caller-transaction append only.
L1 infrastructure/audit/data risk.

## Allowed files

```text
backend/app/modules/outbox/{__init__,models,schemas,repository,service}.py
backend/app/db/models.py
backend/alembic/versions/<next>_shared_transactional_outbox.py
backend/tests/{test_outbox,test_alembic}.py
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-02A.json
```

## Not allowed

```text
Celery/dispatcher/handler/route changes
review, contribution, compensation, AUTH, ART, task or project behavior
new JSON canonicalizer, idempotency framework, dependency or CI weakening
```

## Acceptance criteria

- [ ] Immutable event identity/type/version/project/correlation/causation,
  canonical payload/digest, idempotency key and occurrence time are separate
  from mutable delivery state.
- [ ] Reuse `app.core.hashing.canonical_json_hash` and the existing
  reserve/lock/complete idempotency shape; no second canonicalizer/framework.
- [ ] Caller AsyncSession append flushes but never commits/publishes; changed
  payload under one identity conflicts; PostgreSQL proves duplicate races.
- [ ] No Celery, handler, broker, review, or compensation behavior is added.

## Verification and reviewers

Execute the exact clean isolated CON-02A row in `../RUNTIME_VERIFICATION.md`,
replace its migration placeholder with the one new revision, then run:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_outbox.py tests/test_alembic.py -k 'outbox and (migration or append or idempotency or duplicate or race or rollback)')
(cd backend && .venv/bin/python -m coverage report --include='app/modules/outbox/*' --fail-under=90)
(cd backend && .venv/bin/ruff check app/modules/outbox app/db/models.py tests/test_outbox.py tests/test_alembic.py)
```

Pass requires a non-empty selected test set, PostgreSQL upgrade and guarded
downgrade plus duplicate-race proof, stable exact replay, changed-payload
conflict, caller rollback with no commit/publish, repository coverage at least
78 percent in the same clean run, and focused outbox coverage at least 90
percent. Baseline plus
architecture, security/auth, product/ops, docs, reuse/dedup, test-delta, and CI
integrity are required. Stop before dispatcher behavior.
