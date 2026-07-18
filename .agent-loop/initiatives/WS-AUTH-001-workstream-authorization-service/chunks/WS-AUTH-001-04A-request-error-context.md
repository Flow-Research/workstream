# Chunk Contract: WS-AUTH-001-04A - Request And Error Context

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Add canonical request/correlation context and a stable privacy-bounded error
contract while preserving existing response fields, headers, routes, and
product authorization behavior.

## Risk class and SLA

L1 / P1

## Size circuit breaker

- Stop at 350 changed non-comment production lines for a scope checkpoint.
- Stop and replan above 500 changed non-comment production lines.
- Test, documentation, generated schema, and durable loop evidence lines do not
  count toward the production cap.

## Allowed files

```text
backend/app/main.py
backend/app/core/api_controls.py
backend/app/api/deps/auth.py
backend/app/modules/tasks/router.py
backend/tests/test_api_controls.py
backend/tests/test_app.py
backend/tests/test_auth.py
backend/tests/test_tasks.py
backend/scripts/api_contract_e2e.py
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
database models, migrations, rate counters, or rate-control settings
new routes or rate-control dependency attachments
product permission, role, actor-state, or identity behavior
AUTH-04B, AUTH-05, or later chunk implementation
weakened tests, coverage thresholds, or OpenAPI constraints
BaseHTTPMiddleware, response-body buffering, or response JSON rewriting
```

## Request-context contract

- Inspect raw ASGI header pairs so duplicate `X-Request-ID` or
  `X-Correlation-ID` fields cannot be collapsed by framework parsing.
- Accept zero or one value for each ID. Reject repeated fields, including
  identical duplicates, and reject comma-joined values.
- An accepted ID is exactly 36 ASCII characters and the canonical lowercase,
  hyphenated, non-nil RFC 9562 UUID rendering with RFC variant and version 1
  through 8.
- Generate UUIDv4 for a missing request ID. A missing correlation ID reuses the
  effective request ID.
- Invalid ID input short-circuits before any route or dependency runs and
  returns HTTP 400 `invalid_request`. Generate one fresh UUIDv4 and use it as
  both the safe request ID and safe correlation ID; supplied bytes are never
  reflected.
- Store effective IDs only on the request's ASGI scope state. Concurrent
  requests must not share context.
- Every response, including malformed-ID, 404, 405, validation, authentication,
  unhandled 500, streaming, and background-task responses, returns canonical
  `X-Request-ID` and `X-Correlation-ID` headers. Application-supplied ID response
  headers are overwritten with the effective pair.
- Use pure ASGI middleware that edits only `http.response.start` headers. It
  must preserve status, unrelated duplicate headers, `WWW-Authenticate`,
  `Retry-After`, content length, body chunks, streaming, and background work.

## Error contract

- The canonical nested object has required fields
  `error.code/message/details/correlation_id/retryable`.
- Add the object for explicit API errors, `HTTPException`, request validation,
  coded task-domain JSON errors, auth missing/invalid/unavailable conditions,
  404, 405, 409, 422, future 429/503 errors, and unhandled 500 responses.
- Use the following exact branch mappings. Every unspecified `details` value is
  `{}`. Compatibility `detail`, status, and headers remain as stated below.

| Condition | HTTP | Code | Canonical message | Details | Retryable |
|---|---:|---|---|---|---|
| invalid request/correlation ID | 400 | `invalid_request` | `Invalid request identifier` | `{}` | false |
| request validation | 422 | `invalid_request` | `Request validation failed` | bounded validation summary | false |
| missing bearer token | 401 | `missing_token` | `Missing bearer token` | `{}` | false |
| invalid bearer token | 401 | `invalid_token` | `Invalid bearer token` | `{}` | false |
| verifier unavailable | 503 | `identity_verification_unavailable` | `Identity verification unavailable` | `{}` | true |
| unsupported verified subject kind | 403 | `unsupported_subject_kind` | `Unsupported subject kind` | `{}` | false |
| actor registry unavailable | 503 | `service_unavailable` | `Service unavailable` | `{}` | true |
| coded pre-submit failure | 422 | `pre_submission_checker_failed` | `Pre-submission checks failed` | exact legacy domain details | false |
| coded locked-context failure | 422 | `task_locked_context_invalid` | `Task locked context is invalid` | exact legacy domain details | false |
| other HTTP 400 | 400 | `invalid_request` | `Invalid request` | `{}` | false |
| other HTTP 401 | 401 | `invalid_token` | `Invalid bearer token` | `{}` | false |
| other HTTP 403 | 403 | `permission_not_granted` | `Permission not granted` | `{}` | false |
| other HTTP 404 | 404 | `resource_not_found` | `Resource not found` | `{}` | false |
| other HTTP 405 | 405 | `method_not_allowed` | `Method not allowed` | `{}` | false |
| other HTTP 409 | 409 | `conflict` | `Request conflict` | `{}` | false |
| other HTTP 422 | 422 | `invalid_request` | `Invalid request` | `{}` | false |
| future HTTP 429 | 429 | `rate_limit_exceeded` | `Rate limit exceeded` | `{}` | true |
| other HTTP 503 | 503 | `service_unavailable` | `Service unavailable` | `{}` | true |
| unhandled exception | 500 | `internal_error` | `Internal server error` | `{}` | false |

- Actor-registry domain exceptions retain their existing status and top-level
  `detail`; their nested code/message/retryable values use the matching generic
  status row unless the exact unavailable branch above applies.
- Existing top-level `detail`, `code`, and `details` fields remain present with
  their current types and values. Coded task responses mirror their top-level
  `code/details` into the nested object.
- Preserve status codes and compatibility headers, including exact
  `WWW-Authenticate` and future `Retry-After` values.
- Validation returns at most 20 errors. Each nested item contains only `type`
  and `loc`: `type` is capped at 64 ASCII code characters; `loc` contains at
  most eight integer or string components, with strings capped at 64 ASCII
  characters and unsupported components replaced by `redacted`. The nested
  details shape is `{"errors": [...], "truncated": <boolean>}`.
- The compatibility `detail` remains the existing sanitized list in original
  order for the first 20 errors. Preserve every currently emitted safe
  field/value and validator message, including tested `loc`, constant-redacted
  `input`, and class-name-only exception context. Only the 20-item list cap is
  new; do not truncate locations/messages or remove fields from these retained
  compatibility entries. Submitted input, exception values, and non-finite
  numbers continue to use the existing redaction/JSON-safety helpers. The strict
  eight-location/64-character/type-only privacy shape applies only to nested
  `error.details`.
- Unhandled errors use a constant message, empty details, and
  `retryable=false` in both debug and non-debug modes. No exception, SQL,
  token, claim, provider response, secret, or PII enters a response or log.
- Shared explicit response builders and exception handlers own JSON shapes.
  The request-context middleware must not parse or rewrite response bodies.

## OpenAPI and compatibility contract

- Document the required canonical error object and only the optional legacy
  compatibility fields that routes can actually return.
- Document request/correlation request headers, response ID headers,
  `WWW-Authenticate`, and future `Retry-After` behavior where applicable.
- Existing task coded-error schemas retain `additionalProperties: false`, their
  required top-level fields, and add required canonical `error` through an
  explicit compatible schema or `oneOf` composition.
- No route path, method, response status, or dependency consumer is added,
  removed, or attached by this chunk. Tests inventory the route set and relevant
  dependency consumers before and after the change.

## Behavior proof

- Missing, valid, malformed, non-ASCII, nil, uppercase, non-hyphenated,
  unsupported-version, repeated-identical, repeated-different, and comma-joined
  ID inputs.
- Request-only, correlation-only, both-ID, and concurrent-request isolation.
- Success, validation, 400, 401, 403, 404, 405, 409, 422, representative coded
  task errors, 500, streaming, background task, and duplicate unrelated header
  preservation.
- Exact legacy field/status/header preservation and bounded redaction.
- OpenAPI response-schema validation plus unchanged path/method and dependency
  consumer inventories.
- Test-delta evidence proves existing test files only gain assertions/fixtures:
  no assertion, `pytest.raises`, skip/xfail marker, or `skipTest` line is removed
  or relaxed. New behavior runs through real FastAPI routes and ASGI transport,
  not direct handler-only tests or dependency overrides that bypass middleware.

## Verification commands

```bash
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/python -m pytest -q tests/test_api_controls.py tests/test_app.py tests/test_auth.py tests/test_tasks.py)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/python -m pytest -q --cov=app --cov-report=term-missing tests/test_api_controls.py tests/test_app.py tests/test_auth.py tests/test_tasks.py)
(cd backend && for file in app/core/api_controls.py app/main.py app/api/deps/auth.py app/modules/tasks/router.py; do .venv/bin/coverage report --include="$file" --precision=2 --fail-under=90; done)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python -m pytest -q tests/test_isolated_database_runner.py)
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

Review duplicate-ID rejection, ASGI response preservation, error privacy,
legacy compatibility, OpenAPI truth, and unchanged product authority.

## Stop conditions

- Stop if a response body must be parsed or buffered in middleware.
- Stop if an existing response field/header/assertion would need weakening.
- Stop if production changes exceed the size circuit breaker.
- Stop after the reviewed 04A PR; do not start 04B or AUTH-05 automatically.

## Activation

The user explicitly started parent AUTH-04 on 2026-07-13. Required plan review
split it before implementation. Only this repaired 04A contract was activated,
and runtime edits began only after its required preimplementation re-review
passed.

## Merge result

PR #111 merged the reviewed AUTH-04A implementation to `main` as `90c9a28` on
2026-07-13 after Backend, Agent Gates, CodeRabbit, all required internal
reviewers, and explicit human approval passed. Final branch head was `36c4aa5`;
reviewed production head was `cdcaf77`. AUTH-04B and AUTH-05 remain inactive.
