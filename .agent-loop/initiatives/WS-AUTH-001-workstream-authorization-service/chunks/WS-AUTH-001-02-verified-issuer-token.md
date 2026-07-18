# Chunk Contract: WS-AUTH-001-02 - Verified Issuer Token And JWKS Boundary

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Implement a fail-closed final-token verifier with pinned issuer, audience,
algorithms, JWKS resolution/refresh, temporal claims, subject kind, coarse
scope, and typed verification errors. This chunk authenticates only; it does
not grant Workstream product authority.

## Why this chunk exists

The current production verifier is intentionally unimplemented and the local
HS256 fixture lacks the adopted token contract.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md`

## Risk class

L1

## Preimplementation decisions

- Proposed production dependencies are `PyJWT[crypto]>=2.13,<3.0` for JOSE/JWK
  parsing and asymmetric signature verification, and `httpx>=0.27,<1.0`, moved
  from the development extra to base dependencies, for policy-controlled async
  JWKS and introspection transport. The adapter must not use PyJWT's network
  JWKS client.
- These exact dependency changes remain pending explicit human approval under
  D12. Starting this chunk does not approve them, and no dependency or runtime
  implementation may change until D12 is accepted and recorded.
- `AuthVerifier.verify` returns one `AuthVerificationResult`. Its
  `VerifiedIssuerToken` contains only canonical verified identity and
  coarse-access claims. Separately verified legacy roles may exist only in the
  result's `LegacyAuthorizationCompatibilityContext`.
- `VerifiedIssuerToken` has exactly `issuer`, `subject`, `audience`,
  `expires_at`, `issued_at`, optional `not_before`, `token_id`, `subject_kind`,
  and `scopes`. It has no roles, email, display name, raw claims, relationship
  profiles, claim snapshot, authorization permissions, or grants.
- `subject_kind` is parsed case-sensitively as exactly `human`, `service`,
  `agent`, or `space`. `scope` accepts a space-delimited string or string list,
  normalizes it to an immutable set, and requires `workstream:access` for human
  or `workstream:service` for service. Agent and Space tokens remain canonical
  verified identities only so the dependency can return
  `unsupported_subject_kind`; unknown kinds and kind/scope mismatches fail
  verification.
- `get_current_actor` exposes only `VerifiedIssuerToken`. The sole legacy
  compatibility dependency is `get_registered_actor`, used by the existing
  auth, project, task, and checker routers until their owning cutover chunks.
  A static allowlist test prevents additional consumers.
- Only a human result can build the legacy compatibility context. Service,
  agent, and Space results never receive legacy roles, never reach actor
  registration or product routes, and cannot authorize even when a verified
  token carries `admin`, `worker`, or `project_manager`. `/api/v1/auth/me`
  remains on the legacy dependency during this chunk but no longer exposes
  email, display name, or raw claim snapshots; registration receives only the
  bounded compatibility role snapshot required by unmigrated surfaces.
- The process owns one cached verifier. JWKS and introspection create and close
  separate per-operation HTTP clients through distinct injectable factories;
  neither client nor response escapes its operation.
- Introspection supports exact modes `disabled` and `required`. Production
  rejects an omitted mode. `required` uses OAuth client-secret Basic
  authentication, POSTs the bearer token as form data to one canonical HTTPS
  endpoint, disables redirects and environment proxies, and requires
  `active=true` plus mandatory response `iss`, `sub`, `aud`, and `jti` values
  matching the already verified token. Introspection never supplies or
  replaces identity, kind, or scope claims. JTI-only introspection is not
  supported in this chunk.
- A bounded in-process verifier metrics port emits fixed-name counters through
  a structured logging adapter. Its only labels are closed verification,
  cache, refresh, and introspection result enums; subjects, tokens, `jti`, key
  material, credentials, and URLs are prohibited.
- Stable counters are `workstream_auth_verification_total{result}`,
  `workstream_auth_jwks_cache_total{result}`,
  `workstream_auth_jwks_refresh_total{result}`, and
  `workstream_auth_introspection_total{mode,result}`. The verifier factory owns
  one process-lifetime metrics sink and verifier; tests assert the closed label
  sets and forbidden-value absence.

## Configuration contract

The exact settings and accepted bounds are:

| Environment variable | Type and accepted value | Production default policy |
|---|---|---|
| `WORKSTREAM_TOKEN_ISSUER` | canonical HTTPS URL without userinfo, query, or fragment | required; no default |
| `WORKSTREAM_TOKEN_AUDIENCE` | non-empty string | `workstream` |
| `WORKSTREAM_TOKEN_JWKS_URL` | HTTPS URL without userinfo, query, or fragment | required; no default |
| `WORKSTREAM_TOKEN_ALGORITHMS` | comma-delimited subset of `RS256,RS384,RS512,ES256,ES384,ES512,EdDSA`, from one algorithm family | required; no default |
| `WORKSTREAM_REQUIRED_HUMAN_SCOPE` | one non-empty scope token | `workstream:access` |
| `WORKSTREAM_REQUIRED_SERVICE_SCOPE` | one non-empty scope token | `workstream:service` |
| `WORKSTREAM_TOKEN_CLOCK_SKEW_SECONDS` | integer `0..300` | `30` |
| `WORKSTREAM_TOKEN_MAX_BYTES` | integer `512..32768` | `16384` |
| `WORKSTREAM_TOKEN_HEADER_MAX_BYTES` | integer `128..8192` and not above token max | `4096` |
| `WORKSTREAM_TOKEN_PAYLOAD_MAX_BYTES` | integer `256..24576` and not above token max | `12288` |
| `WORKSTREAM_TOKEN_JWKS_CACHE_TTL_SECONDS` | integer `30..3600` | `300` |
| `WORKSTREAM_TOKEN_JWKS_MAX_RESPONSE_BYTES` | integer `1024..1048576` | `262144` |
| `WORKSTREAM_TOKEN_JWKS_MAX_KEYS` | integer `1..100` | `20` |
| `WORKSTREAM_TOKEN_UNKNOWN_KID_CACHE_TTL_SECONDS` | integer `1..300` | `30` |
| `WORKSTREAM_TOKEN_UNKNOWN_KID_CACHE_MAX_ENTRIES` | integer `1..1000` | `100` |
| `WORKSTREAM_TOKEN_JWKS_CONNECT_TIMEOUT_SECONDS` | float `0.1..10` | `2` |
| `WORKSTREAM_TOKEN_JWKS_READ_TIMEOUT_SECONDS` | float `0.1..10` | `3` |
| `WORKSTREAM_TOKEN_JWKS_WRITE_TIMEOUT_SECONDS` | float `0.1..10` | `3` |
| `WORKSTREAM_TOKEN_JWKS_POOL_TIMEOUT_SECONDS` | float `0.1..10` | `1` |
| `WORKSTREAM_TOKEN_JWKS_TOTAL_TIMEOUT_SECONDS` | float `0.5..15` | `5` |
| `WORKSTREAM_TOKEN_INTROSPECTION_MODE` | exactly `disabled` or `required` | required; no default |
| `WORKSTREAM_TOKEN_INTROSPECTION_DISABLED_REASON` | non-empty issuer-policy evidence reference | required only in `disabled` mode |
| `WORKSTREAM_TOKEN_INTROSPECTION_URL` | HTTPS URL without userinfo, query, or fragment | required only in `required` mode |
| `WORKSTREAM_TOKEN_INTROSPECTION_CLIENT_ID` | non-empty secret-backed string | required only in `required` mode |
| `WORKSTREAM_TOKEN_INTROSPECTION_CLIENT_SECRET` | non-empty secret-backed value | required only in `required` mode |
| `WORKSTREAM_TOKEN_INTROSPECTION_MAX_RESPONSE_BYTES` | integer `256..262144` | `65536` |
| `WORKSTREAM_TOKEN_INTROSPECTION_CONNECT_TIMEOUT_SECONDS` | float `0.1..10` | `2` |
| `WORKSTREAM_TOKEN_INTROSPECTION_READ_TIMEOUT_SECONDS` | float `0.1..10` | `3` |
| `WORKSTREAM_TOKEN_INTROSPECTION_WRITE_TIMEOUT_SECONDS` | float `0.1..10` | `3` |
| `WORKSTREAM_TOKEN_INTROSPECTION_POOL_TIMEOUT_SECONDS` | float `0.1..10` | `1` |
| `WORKSTREAM_TOKEN_INTROSPECTION_TOTAL_TIMEOUT_SECONDS` | float `0.5..15` | `5` |

Production, staging, and preview reject startup when a required value or
explicit mode is missing, the issuer retains a placeholder value, an endpoint
is not HTTPS, an algorithm is symmetric/unknown/mixed-family, related size
bounds are inconsistent, or a numeric bound is outside this table. PyJWT
receives algorithms only from this trusted configuration and explicitly
requires every mandatory claim.

## Network and cache policy

- JWKS and introspection endpoints reject userinfo, query strings, and
  fragments. Introspection uses its configured path and exact origin. JWKS
  requires HTTPS except for an injected deterministic local-test transport.
- Both clients set `follow_redirects=False`, `trust_env=False`, bounded
  connect/read/write/pool timeouts, and an outer `asyncio.timeout` total
  deadline. Responses are streamed and rejected as soon as the byte limit is
  exceeded.
- JWKS enforces configured byte, key-count, and cache-TTL bounds. Eligible keys
  require a non-empty unique `kid`, pinned `alg`, compatible asymmetric `kty`,
  signature `use` when present, and `verify` in `key_ops` when present.
- Tokens have bounded total/header/payload sizes and reject token-supplied
  remote-key headers including `jku` and `x5u`.
- A verifier-owned async lock single-flights refresh. A request rechecks the
  cache after acquiring the lock and performs at most one network refresh for
  an unknown `kid`. Refresh failure never turns an unknown key into a cache
  hit, and expired cache data is not used.
- A bounded TTL/LRU negative-`kid` cache suppresses repeated refreshes without
  retaining unbounded attacker input. Rotation replaces the eligible key set
  atomically while an unexpired matching key remains usable until refresh is
  required.

## Verification proof matrix

Focused tests must cover malformed JWT/header/claims; `none`, unpinned, and
confused algorithms; missing, duplicate, and unknown `kid`; exactly-one and
single-flight refresh; invalid, oversized, excessive, incompatible, rotated,
expired, and unavailable JWKS data; missing/wrong issuer, audience, subject,
`jti`, subject kind, and scope; expired/future `exp`, `iat`, and `nbf` with skew
boundaries; distinct human/service scopes; retained agent/Space kinds; every
introspection HTTP, redirect, timeout, oversize, malformed, inactive, issuer,
subject, audience, and JTI mismatch path; credential/token redaction; bearer
absence from JWKS and
redirect targets; and rejection of local HMAC/dev fixtures outside local/test.
Tests use injected transports and perform no DNS or real network access.

## SLA

P1

## Allowed files

```text
backend/pyproject.toml
backend/app/core/config.py
backend/app/core/auth.py
backend/app/main.py
backend/app/interfaces/auth.py
backend/app/adapters/auth/**
backend/app/api/deps/auth.py
backend/app/schemas/auth.py
backend/tests/test_auth.py
backend/tests/test_config.py
backend/tests/test_actors.py
backend/tests/test_tasks.py
backend/scripts/api_contract_e2e.py
docs/operations_authorization_service.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
actor/grant database models or migrations
product permission checks
project/task/checker authorization changes
Workstream token issuance, login, sessions, or passwords
trusting token role claims
```

## Contract amendment A1

Implementation evidence exposed two directly related boundaries omitted from
the initial allowlist. `backend/tests/test_actors.py` and
`backend/tests/test_tasks.py` contain the stale identity-metadata expectations
created by the approved canonical-token minimization, and `backend/app/main.py`
owns the required production startup rejection. They are allowed only for
those exact purposes. The amendment is explicitly recorded as a process repair
and requires the full reviewer fanout before PR publication; it does not
authorize actor-service, persistence, route-policy, or unrelated app-factory
changes.

## Contract amendment A2

Internal docs review found that canonical `docs/spec_authorization_service.md`
still described the now-mandatory verified token identifier as optional. That
file is allowed only to make `jti` mandatory and document that compatibility
actor responses no longer copy issuer email or display name. This closes
canonical contract drift; it does not change actor persistence or APIs.

## Acceptance criteria

- `VerifiedIssuerToken` contains only verified identity/coarse-access claims.
- Signature, issuer, audience, `exp`, `iat`, optional `nbf`, `jti`,
  `subject_kind`, and required scope are validated.
- Credential-invalid and inactive-token failures map publicly to 401. Typed
  verifier configuration, JWKS, and introspection unavailability fail closed
  with a non-secret 503; internal error types never include bearer material.
- Algorithms are configured and pinned; unknown `kid` triggers at most one
  controlled refresh.
- Valid cached keys obey bounded cache policy; unavailable verification fails
  closed.
- An explicit introspection/revocation mode is configured. Production rejects
  an unspecified mode; disabled mode is explicit and evidence-backed by issuer
  policy. Enabled bearer-token introspection uses a separately configured,
  allowlisted HTTPS endpoint, POSTs only to that origin, follows no redirects,
  has strict connect/read/total timeout and response-size bounds, and redacts
  request credentials and responses from logs/errors. A `jti`-only issuer
  contract is not supported by this chunk.
- JWKS retrieval and credential-bearing introspection use separate clients and
  policies. JWKS requires HTTPS outside deterministic local tests, follows no
  redirects, and enforces response-size and key-count bounds. Tests prove a
  bearer token never reaches JWKS or any redirect target.
- Human/service scope differs; agent and Space kinds are represented for the
  resolver to deny later.
- Token roles do not appear in the verified authority contract.
- The existing `AuthVerifier` protocol/factory is evolved in place; no second
  TokenVerifier hierarchy is created.
- Untouched legacy product surfaces receive one explicitly named
  `LegacyAuthorizationCompatibilityContext` built only after successful final
  token verification. It may expose verified legacy role claims only to an
  enumerated shrinking allowlist of unmigrated dependencies. Migrated surfaces
  cannot import or consume it, and chunk 15 removes it completely.
- The API drill is updated to emit the final token claim shape (`jti`,
  `subject_kind`, scope, issuer/audience/time) while retaining legacy roles only
  for the bounded compatibility context. Intake remains executable and no test
  treats the canonical verified-token type as role authority.
- Dev/local fixtures remain impossible in staging/production.
- Any production dependency addition is narrowly justified and reviewed.
- No production dependency is added until explicit human approval is durably
  recorded; absence of that approval stops the chunk.
- A clean base-dependency installation imports PyJWT cryptography and HTTPX,
  passes `pip check`, and runs focused auth/config tests before the full suite.
- The operations runbook assigns ownership for issuer/JWKS configuration, key
  rotation, cache bounds, introspection policy, outage response, and evidence.
- The runbook inventories every canonical environment variable from the
  configuration contract, accepted bounds, exact introspection modes,
  client-secret ownership/rotation, algorithms, subject-kind/scope policy,
  metric names, alert thresholds, diagnosis, escalation, and evidence commands.
- Bounded-cardinality metrics for verification result, JWKS cache hit/refresh,
  refresh failure, and introspection result are emitted at the verifier boundary
  without issuer subject, token, `jti`, key material, or raw URL labels.

## Verification commands

```bash
(tmp_venv="$(mktemp -d)" && trap 'rm -rf "$tmp_venv"' EXIT && python3 -m venv "$tmp_venv" && "$tmp_venv/bin/python" -m pip install -e ./backend && "$tmp_venv/bin/python" -c 'import jwt, cryptography, httpx' && "$tmp_venv/bin/python" -m pip check)
(cd backend && .venv/bin/python -m pytest -q tests/test_auth.py tests/test_config.py)
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

Inspect algorithm pinning, JWKS outage behavior, cache refresh, scope/subject
classification, dependency choice, and absence of role authority.

## Stop conditions

Stop if verification requires accepting unverified claims, permissive algorithm
selection, a shared production HMAC secret, forwarding bearer tokens anywhere
except the separately approved/configured introspection origin under the rules
above, a second verifier hierarchy, or an unapproved production dependency.
