# Chunk Contract: WS-AUTH-001-10B1 — Durable Authorization Read Rate Control

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Extend the existing privacy-keyed PostgreSQL API rate-control system with one
closed `authorization_read` scope before sensitive authorization reads exist.

## Why this chunk exists

First-access and administrative-mutation counters have different threat and
capacity semantics. Sensitive reads need their own cross-replica abuse budget
without an ad hoc limiter or a public route in the migration change.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md`
- Decision: D33

## Risk class

L1 authorization, privacy, migration, and API abuse control.

## SLA

P1

## Allowed files

```text
backend/alembic/versions/0033_authorization_read_rate_control.py
backend/app/modules/api_controls/**
backend/app/api/deps/api_controls.py
backend/app/core/config.py
backend/tests/test_alembic.py
backend/tests/test_api_rate_controls.py
backend/tests/test_config.py
.github/workflows/backend.yml
scripts/test_agent_gates.py
docs/operations_authorization_service.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-10B1.json
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
authorization candidate/grant routes or action activation
pagination cursor implementation or secret
project-role read queries or response schemas
issue/revoke, PREP, idempotency, or invalidation changes
new counter table, cache, in-memory limiter, or external rate service
workflow changes except adding the API-controls 90 percent coverage gate
lowering, replacing, or broadening exclusions in any coverage threshold
```

## Acceptance criteria

- Migration `0032` changes only the current counter scope constraint from exact
  `first_access|admin_mutation` to exact
  `first_access|admin_mutation|authorization_read`. Historical migrations stay
  immutable; upgrade preserves rows; downgrade refuses while new-scope rows
  exist and otherwise restores the prior constraint. Downgrade takes an
  appropriate table lock before its row check and DDL so no concurrent consumer
  can cross the refusal check. Deterministic lock-order/concurrency proof uses
  independent sessions and no timing sleeps.
- Typed `RATE_SCOPES` gains exactly `authorization_read`; existing HMAC domain,
  framed issuer/subject digest, committed session, database-time window,
  pruning, and fail-closed behavior are reused unchanged.
- Dedicated `api_authorization_read_rate_limit` defaults to 120 and accepts
  1..10,000. `api_authorization_read_rate_window_seconds` defaults to 60 and
  accepts 1..3,600. They use the existing API-rate key only; cursor/auth secrets
  are never fallbacks. Tests cover defaults, bounds, underflow, overflow, and
  independence from both existing scopes.
- One unattached `enforce_authorization_read_rate_limit` dependency consumes the
  exact scope and preserves canonical 429/Retry-After and retryable 503 behavior.
- Tests prove scope separation, identity privacy, exact limit/exceeded/reset,
  concurrent sessions, cross-replica behavior, commit/database/missing-secret
  failures, bounded config, migration round trip/refusal, and unchanged scopes.
- No permission, action, route, or OpenAPI availability changes.
- GitHub Backend adds a distinct 90 percent coverage report covering
  `app/modules/api_controls/*` and `app/api/deps/api_controls.py`; existing
  reports and thresholds remain byte-for-byte unchanged. Zero action/OpenAPI
  delta is asserted.
- Operations/spec docs cover `0032` upgrade and downgrade preflight, refusal
  with live read counters, forward recovery, limit/window settings, shared
  privacy HMAC key and secret separation, 429/Retry-After, retryable 503, and
  the intentionally unattached/no-action rollout state.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/api_controls app/api/deps/api_controls.py app/core/config.py tests/test_api_rate_controls.py tests/test_config.py tests/test_alembic.py alembic/versions/0033_authorization_read_rate_control.py)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python scripts/run_isolated_tests.py --metadata-json <path> --timeout-seconds 300 -- .venv/bin/python -m pytest -q tests/test_api_rate_controls.py tests/test_config.py tests/test_alembic.py -k 'authorization_read or api_rate_control')
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

GitHub owns the full sharded suite, aggregate 78 percent coverage, the new exact
API-controls 90 percent gate, migration proof, API E2E, and Agent Gates.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Review one-scope migration, privacy-key reuse, capacity settings, cross-replica
proof, downgrade refusal, and absence of routes.

## Stop conditions

Stop on a second limiter/store, raw identity persistence, non-database time,
shared first-access/mutation budget, route attachment, or migration data loss.
