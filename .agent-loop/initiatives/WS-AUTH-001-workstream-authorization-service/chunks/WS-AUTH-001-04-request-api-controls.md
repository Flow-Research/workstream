# Chunk Contract: WS-AUTH-001-04 - Request, Error, And API Control Foundation

## Status

Split before implementation after required plan review. This parent is not an
implementation contract. Its authorized children are `WS-AUTH-001-04A` and
`WS-AUTH-001-04B`; only 04A is currently active.

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Introduce request/correlation context, the stable structured error envelope,
and Postgres-backed security endpoint rate controls without changing product
authorization.

## Why this chunk exists

First-access and authority-management APIs require consistent request evidence,
private errors, and cross-replica abuse controls before they ship.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/main.py
backend/app/api/deps/**
backend/app/core/api_controls.py
backend/app/core/config.py
backend/app/modules/api_controls/**
backend/app/db/models.py
backend/alembic/versions/0017_*.py
backend/tests/test_app.py
backend/tests/test_auth.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
actor/profile migration or first-access behavior
authority audit/idempotency/grant models
permission evaluation or product authorization cutover
dependency overrides that bypass the real request path
```

## Acceptance criteria

- Every request has validated request/correlation IDs with safe generation and
  propagation rules.
- `X-Request-ID` and `X-Correlation-ID` accept one canonical UUID value each;
  absent request IDs are generated, absent correlation IDs reuse the effective
  request ID, and malformed/duplicate values fail as `invalid_request` without
  reflecting the supplied bytes.
- Successful and error responses return the effective request/correlation IDs
  in headers. The structured error object contains the correlation ID only.
- Errors use a stable envelope without raw exception, token, claims, or PII.
- The envelope is `error.code/message/details/correlation_id/retryable`.
  Existing `detail`, `code`, and `details` fields remain additively compatible
  during the bounded migration so current intake clients and tests do not break.
- Postgres-backed rate controls work across replicas, use privacy-safe keys and
  database time, and are configurable for first access/admin mutations.
- `backend/app/modules/api_controls` owns feature models, persistence queries,
  and the rate-control service. Middleware/dependencies invoke that service;
  generic core/API helpers do not own SQL or transaction policy.
- Allowed requests proceed, exceeded limits return stable 429, and unavailable
  controls fail closed without bypassing protected operations.
- Migration owns counter constraints/indexes/database-time fields and proves
  prior-head upgrade, downgrade, and re-upgrade.
- The rate-control table has one atomic fixed-window counter per control scope
  and HMAC-SHA256 subject key. The repository owns PostgreSQL upsert/database
  time; the service owns key derivation and limit decisions.
- Rate-control invocation without its configured secret or with unavailable
  persistence returns a retryable safe 503. Exceeded controls return a stable
  retryable 429 with a bounded `Retry-After` value.
- AUTH-04 exposes named first-access and admin-mutation control dependencies for
  their later owning endpoints but does not attach them to unrelated legacy
  reads or implement those future endpoints.
- Full backend suite and the intentionally updated API contract drill preserve
  the existing intake lifecycle and error compatibility.

## Verification commands

```bash
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic upgrade head)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic downgrade -1)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic upgrade head)
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Review error compatibility/privacy, rate-limit keying/failure behavior,
database-time semantics, and unchanged product authority.

## Stop conditions

Stop if rate controls require a new production dependency without explicit
human approval or if existing intake assertions must be weakened.

## Activation

AUTH-03 post-merge memory merged through PR #110 as `1864867`. The user
explicitly started AUTH-04 on 2026-07-13. Discovery found that parallel artifact
work already owns migration `0016`, so this chunk uses additive migration
`0017_api_controls` from `0016_artifact_domain`; this is a sequence correction,
not a scope expansion.

## Split implementation plan

1. Implement and merge 04A request/error context under its repaired contract.
2. Update post-merge memory and stop.
3. Start 04B only after a separate explicit user signal; implement its durable
   rate controls and migration under its own reviewed contract.
4. Do not start AUTH-05 automatically after either child.
