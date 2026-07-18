# Chunk Contract: WS-AUTH-001-04B - PostgreSQL Rate Controls

## Status

Merged through PR #113 as `05a63c8` on 2026-07-14 after required internal
review, Backend, Agent Gates, CodeRabbit, and explicit human approval passed.

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Provide privacy-keyed, cross-replica PostgreSQL fixed-window rate controls for
future first-access and authority-management mutations without attaching them
to routes owned by later chunks.

## Risk class and SLA

L1 / P1

## Size circuit breaker

- Stop at 350 changed non-comment production lines for a scope checkpoint.
- Stop and replan above 500 changed non-comment production lines.
- Production count includes `backend/app/**` and the Alembic migration. Tests,
  docs, and `.agent-loop` evidence do not count.

## Allowed files

```text
backend/app/core/config.py
backend/app/api/deps/api_controls.py
backend/app/modules/api_controls/__init__.py
backend/app/modules/api_controls/models.py
backend/app/modules/api_controls/repository.py
backend/app/modules/api_controls/service.py
backend/app/db/models.py
backend/alembic/versions/0017_api_controls.py
backend/tests/test_api_rate_controls.py
backend/tests/test_auth.py
backend/tests/test_config.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/operations_authorization_service.md
docs/architecture_data_model.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/PLAN.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/chunks/WS-ART-001-02A1-external-service-adapter-foundation.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
request/error-context implementation owned by AUTH-04A
new routes or attachment to unrelated existing routes
first-access, grant, actor-state, or product authorization behavior
Redis/in-memory counters or persisted raw identity/network/token material
AUTH-05 or later chunk implementation
```

## Persistence and transaction contract

- Create only `api_rate_control_counters` with `control_scope VARCHAR(32)`,
  `key_digest BYTEA`, `window_started_at TIMESTAMPTZ`,
  `window_expires_at TIMESTAMPTZ`, `request_count BIGINT`, and
  `updated_at TIMESTAMPTZ`, all non-null. The composite primary key is
  `(control_scope, key_digest)`; there is no actor or surrogate identifier.
- Name the constraints `pk_api_rate_control_counters`,
  `ck_api_rate_control_counters_scope_token`,
  `ck_api_rate_control_counters_digest_length`,
  `ck_api_rate_control_counters_request_count`, and
  `ck_api_rate_control_counters_window_order`. They enforce the composite key,
  exact scope tokens, `octet_length(key_digest) = 32`, `request_count between 1
  and 9223372036854775807`, and `window_started_at < window_expires_at`. Create
  `ix_api_rate_control_counters_window_expires_at`, which is consumed by the
  pruning query.
- Windows are first-consumption-anchored fixed windows. One PostgreSQL upsert
  binds a `clock` CTE to one `statement_timestamp()` value. It inserts count 1;
  on conflict it resets start/end/count when existing `window_expires_at <=`
  database now, otherwise it increments. Active-window saturation must use
  `CASE WHEN request_count = 9223372036854775807 THEN request_count ELSE
  request_count + 1 END`; never evaluate max plus one. New expiry is database
  now plus parameterized `make_interval(secs => :window_seconds)`.
- The one statement returns the CTE database now, persisted window start/end,
  and persisted count. `updated_at` is set to that same CTE database timestamp
  on insert, expiry reset, ordinary increment, and saturated denial. All ORM
  timestamps are timezone aware.
- Counts `1..limit` allow. Count `limit+1` and later deny and remain durably
  consumed. `Retry-After` is the ceiling of remaining database-time seconds,
  clamped to integer `1..window_seconds`; application time is never consulted.
- The service accepts an injectable async session factory whose production
  default is the existing `get_session_factory()`. Every consume opens an
  independent short-lived session, performs bounded pruning plus the upsert,
  and commits before returning a decision. The dependency may construct/raise
  429 only after the committed decision returns. Downstream rollback cannot
  undo consumption.
- Session-open, prune, execute, and commit `SQLAlchemyError` failures map to one
  local unavailable error and then a constant retryable structured 503. The
  existing `get_session_factory()` missing-database `RuntimeError` maps narrowly
  by its exact stable configuration failure; every other `RuntimeError` is
  re-raised. A failed transaction is rolled back without overriding the stable
  error. Cancellation and other `BaseException` values propagate. Tests cover
  absent database configuration separately from open/execute/commit failures.

## Privacy and configuration contract

- The exact server-owned scope tokens are ASCII `first_access` and
  `admin_mutation`; callers cannot supply another scope.
- Derive `key_digest` with HMAC-SHA256. The key setting is a Pydantic
  `SecretStr` containing canonical padded RFC 4648 Base64. Decode strictly with
  no whitespace or alternate encoding; require 32..64 decoded bytes and the
  canonical re-encoding to equal the supplied ASCII string. Pydantic repr and
  validation errors must never expose the value.
- The HMAC preimage is exactly
  `len(domain)||domain||len(scope)||scope||len(issuer)||issuer||len(subject)||subject`,
  in that order. Every length is an unsigned four-byte big-endian byte length.
  Domain is exact ASCII `workstream-api-rate/v1`; scope is its exact ASCII
  token; issuer and subject are exact UTF-8. Do not trim, case-fold, or Unicode
  normalize. Enforce issuer and subject independently at 1..4096 UTF-8 bytes
  before framing. Commit literal known-answer vectors and collision-separation
  tests that do not calculate expected values through the production helper.
- Persist only scope and digest. Never persist or log raw issuer, subject,
  actor ID, email, role, token, claims, or network address.
- Expose `api_rate_limit_key_secret` as `SecretStr | None`, backed by private
  settings storage after constructor, environment, or dotenv input is removed
  from Pydantic's structured validation graph. There is no non-null fallback
  and no generated secret. Present
  malformed, non-ASCII, noncanonical, whitespace-bearing, too-short, or
  too-long values fail settings construction. Unrelated Pydantic failures and
  alternate `model_validate`, `model_validate_json`, and
  `model_validate_strings` entry points must not retain the raw key in
  structured error APIs, recoverable `SecretStr` objects, or exception cause/
  context graphs. Malformed settings JSON fails with a constant error that does
  not retain the supplied document anywhere in its exception graph. Layered
  dotenv files preserve BaseSettings' later-file precedence.
- Exact numeric settings are `api_first_access_rate_limit=10`,
  `api_first_access_rate_window_seconds=60`,
  `api_admin_mutation_rate_limit=30`, and
  `api_admin_mutation_rate_window_seconds=60`, with limit bounds `1..10000` and
  window bounds `1..3600`.
- Missing secret remains startup-compatible while no route is attached, but
  invoking a protected dependency without it returns structured HTTP 503 with
  code `service_unavailable`, message/detail `Service unavailable`, empty
  details, and `retryable=true`. Database unavailability uses the same response.
- Secret rotation intentionally resets effective counters. The runbook requires
  quiescing every protected write for at least the largest effective
  pre-rotation window configured on any replica, rotating every replica while
  writes remain quiesced, pruning expired rows, and only then resuming.
  Mixed-secret replicas must never serve protected writes.

## Retention contract

- The service owns bounded opportunistic pruning in the same dedicated
  transaction after its upsert: delete at most 100 other rows ordered by expiry
  whose `window_expires_at <= statement_timestamp()`, using row locking with
  `SKIP LOCKED`. Upsert-first lock ordering ensures a concurrently consumed key
  is already active/locked and skipped rather than creating a two-key lock
  cycle. A synchronized two-expired-key PostgreSQL test proves no deadlock or
  503.
- Expired rows are no longer rate authority. The runbook owns an operator
  cleanup command for idle systems and secret rotation; it deletes only expired
  rows by database time. Tests prove pruning is bounded, concurrent-safe, and
  never persists or emits identity material.

## Route boundary and behavior proof

- Export named first-access and admin-mutation dependencies for later owning
  chunks, but attach neither dependency here.
- Each dependency consumes only `AuthVerificationResult.token.issuer` and
  `.subject` from `get_auth_verification_result`. It must not consume
  `ActorContext`, `get_registered_actor`, actor ID, roles, email, or an
  issuer-specific adapter. Scope, limit, and window are server constants plus
  validated settings.
- A verified issuer or subject outside the local 1..4096 UTF-8 byte boundary is
  treated as the same non-echoing local unavailable condition and structured
  retryable `service_unavailable` 503, never an unhandled 500.
- A denied dependency raises `StructuredHTTPException` 429 with code
  `rate_limit_exceeded`, message/detail `Rate limit exceeded`, empty details,
  `retryable=true`, and canonical integer `Retry-After`. Reuse 04A handlers and
  database/session infrastructure; introduce no parallel error or DB layer.
- Inventory path/method and the recursive dependency graph to prove no
  production route or consumer changed. Exercise dependencies only through
  test-only FastAPI routes using real ASGI transport and 04A handlers.
- Prove allow, exact limit, repeated exceed, expiry reset, distinct key/scope,
  concurrent increments, cross-session visibility, downstream rollback
  independence, missing/malformed secret, database unavailable, bounded
  `Retry-After`, subsecond and application-clock-skew behavior, and privacy-safe
  persistence/logging.
- Synchronized real-PostgreSQL concurrency uses independently created sessions
  with `N > limit` and proves exactly `limit` allows, `N-limit` denials, final
  durable count `N`, repeated-denial consumption, no lost increments, and
  saturation at BIGINT max without overflow.

## Migration proof

- `0017_api_controls` revises `0016_artifact_domain`.
- Seed representative existing `0016` domain rows and prove they survive the
  upgrade unchanged. Prove every named primary-key/check/index contract and
  reject invalid direct inserts.
- Downgrade must query the rate table and raise a bounded `RuntimeError` when it
  is nonempty. PostgreSQL/Alembic transaction rollback must leave its rows,
  table, and revision at `0017`. After explicit test-only cleanup, prove empty
  `0017 -> 0016 -> 0017` succeeds. Never claim a rate row survives a successful
  downgrade that drops its table.

## Verification commands

```bash
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/python -m pytest -q tests/test_api_rate_controls.py tests/test_config.py tests/test_alembic.py)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/python -m pytest -q --cov=app.modules.api_controls --cov=app.api.deps.api_controls --cov=app.core.config --cov-report=term-missing tests/test_api_rate_controls.py tests/test_config.py tests/test_alembic.py)
(cd backend && for file in app/core/config.py app/api/deps/api_controls.py app/modules/api_controls/models.py app/modules/api_controls/repository.py app/modules/api_controls/service.py; do .venv/bin/coverage report --include="$file" --precision=2 --fail-under=90; done)
(cd backend && .venv/bin/python scripts/run_isolated_tests.py --metadata-json <temp-metadata-json> --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78)
(cd backend && .venv/bin/python scripts/run_isolated_tests.py --metadata-json <temp-metadata-json> --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/python scripts/api_contract_e2e.py)
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && .venv/bin/docstr-coverage --config .docstr.yaml)
python3 scripts/check_loop_memory_state.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/test_agent_gates.py
git diff --unified=0 origin/main...HEAD -- backend/tests | (! rg '^-(.*assert|.*pytest\.raises|.*pytest\.mark\.(skip|xfail)|.*skipTest)')
git diff --check
```

`backend/tests/test_auth.py` was added as a test-only scope amendment after the
implemented canonical-verification consumer correctly tripped its static
consumer allowlist. The amendment may update only that allowlist for the new
unattached `api/deps/api_controls.py` consumer; it does not permit auth runtime,
route, compatibility, or authority changes.

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

## Stop conditions

- Stop if a rate count can be rolled back with downstream work.
- Stop if atomic database-time semantics cannot be proven under concurrency.
- Stop if a raw identity or token-derived value would be persisted or logged.
- Stop if production changes exceed the size circuit breaker.
- Stop after 04B; do not start AUTH-05 automatically.

## Activation

AUTH-04A post-merge memory merged through PR #112 as `7749f54`. The user
explicitly started AUTH-04B on 2026-07-13. Required L1 preimplementation review
passed the second repaired contract at `b5dceb1` before runtime edits.

## Merge result

Final branch head `94fb2fe` merged to `main` through PR #113 as `05a63c8`.
GitHub Backend passed 937 tests at 82.15 percent global coverage, artifact
foundation coverage passed at 91.07 percent, and Agent Gates and CodeRabbit
passed. AUTH-05 remains inactive pending this post-merge memory update and a
separate explicit user start.
