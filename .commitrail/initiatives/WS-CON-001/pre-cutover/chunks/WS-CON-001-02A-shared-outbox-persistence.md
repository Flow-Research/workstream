# Chunk Contract: WS-CON-001-02A - Shared Transactional Outbox Persistence

## Goal and risk

Land feature-neutral PostgreSQL outbox truth and caller-transaction append only.
L1 infrastructure/audit/data risk.

## Allowed files

```text
backend/app/modules/outbox/{__init__,models,schemas,repository,service}.py
backend/app/db/models.py
backend/alembic/versions/<next>_shared_transactional_outbox.py
backend/tests/{test_outbox,test_alembic,assertion_helpers,test_assertion_helpers}.py
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

- [x] Immutable event identity/type/version/project/correlation/causation,
  canonical payload/digest, idempotency key and occurrence time are separate
  from mutable delivery state.
- [x] Reuse `app.core.hashing.canonical_json_hash` and the existing
  reserve/lock/complete idempotency shape; no second canonicalizer/framework.
- [x] Caller AsyncSession append flushes but never commits/publishes; changed
  payload under one identity conflicts; PostgreSQL proves duplicate races.
- [x] No Celery, handler, broker, review, or compensation behavior is added.

## Verification and reviewers

Required reviewers are senior engineering, QA/test, security/auth,
product/ops, architecture, docs, reuse/dedup, test delta, and CI integrity.
Every track must review the exact implementation SHA and resolve or document
all valid findings before publication.

Execute the bounded local CON-02A row in `../RUNTIME_VERIFICATION.md`, replace
its migration placeholder with the one new revision, then run:

```bash
metadata_dir="$(mktemp -d)"
trap 'rm -rf "$metadata_dir"' EXIT
(cd backend && .venv/bin/python -m coverage erase)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 900 -- .venv/bin/python -m pytest -q tests/test_outbox.py tests/test_alembic.py -k outbox --cov=app --cov-report=)
(cd backend && .venv/bin/python -m coverage report --include='app/modules/outbox/*' --fail-under=90)
(cd backend && .venv/bin/ruff check app/modules/outbox app/db/models.py tests/assertion_helpers.py tests/test_assertion_helpers.py tests/test_outbox.py tests/test_alembic.py alembic/versions/0029_shared_transactional_outbox.py)
```

Local pass requires a non-empty selected test set, PostgreSQL upgrade and guarded
downgrade plus duplicate-race proof, stable exact replay, changed-payload
conflict, caller rollback with no commit/publish, and focused outbox coverage at
least 90 percent. The pushed full PR must then pass the existing GitHub Backend
full-suite job, including repository coverage at least 78 percent. Baseline plus
architecture, security/auth, product/ops, docs, reuse/dedup, test-delta, and CI
integrity are required. Stop before dispatcher behavior.
