# Workstream MCP Adapter

An independently installed adapter exposing nine tools under the caller's authority:

- `workstream_profile_get` calls `GET /api/v1/actors/me`.
- `workstream_profile_update` calls the unkeyed `PATCH /api/v1/actors/me`.
- `workstream_authorization_context_get` calls
  `GET /api/v1/actors/me/authorization-context` for one supplied project.
- `workstream_permissions_list` calls `GET /api/v1/authorization/permissions`.
- `workstream_admin_roles_list` calls `GET /api/v1/authorization/admin-role-definitions`.
- `workstream_admin_grants_list` calls `GET /api/v1/admin-role-grants`.
- `workstream_actor_admin_grants_list` calls
  `GET /api/v1/actors/{actor_profile_id}/admin-role-grants`.
- `workstream_actor_get` calls `GET /api/v1/actors/{actor_profile_id}`.
- `workstream_actor_identity_link_get` calls
  `GET /api/v1/actors/{actor_profile_id}/identity-links`.

Each call forwards the caller's bearer to its fixed public Workstream operation.
There are no MCP resources, prompts or administrative mutation tools in this package.

## Authentication Boundary

This is the maintainer-approved **custom bearer-header integration**, not the
standard remote MCP OAuth authorization profile. Use a client that can send an
explicit `Authorization: Bearer <Workstream access token>` header on every tool
invocation. OAuth discovery and compatibility with hosted clients that require
that discovery are not provided.

The caller obtains and refreshes its token through the existing identity flow.
The adapter rejects missing, duplicate or malformed headers, then forwards a
well-formed bearer unchanged to the configured API. Workstream verifies the
signature, issuer, audience and expiry and applies its current actor and access
rules. The adapter does not call Flow, inspect JWT claims, hold refresh tokens,
create grants or perform an extra authentication API call.

Initialization and tool listing reveal only the static catalogue. They do not
authenticate a session. Tokens never belong in tool arguments, URLs, logs or
prompts. An AI client using a human bearer acts as that human; this is not future
agent registration or delegation.

## Local Run

Python 3.12 and uv are required. From this directory:

```bash
uv sync --frozen --extra dev
WORKSTREAM_API_URL=http://127.0.0.1:8000 uv run --frozen workstream-mcp
```

The endpoint is `http://127.0.0.1:8080/mcp`. The default listener is loopback.
Configuration is read from environment variables; `.env.example` documents
the settings but is not loaded automatically. No server-wide caller token is
configured. A separate Workstream API must already be running.

The profile read takes `{}`. Profile update accepts at least one of
`display_name` and `contact_email`, preserving omission and explicit `null` while
matching Workstream's normalization and bounds. Authorization context requires
one `project_id`; Workstream decides whether the caller may see that exact
project. First admission can create the actor/link and update admission
timestamps, but does not grant roles. Lifecycle and access denials follow
Workstream. Errors are MCP tool failures with safe status/code information, not
fabricated results.

Definition tools take `{}` and return definitions, not the caller's effective
permissions. Actor reads require a UUID `actor_profile_id`. Grant lists require
`scope_type` (`system` or `project`), with `scope_project_id` for project scope;
the actor-history tool also requires `actor_profile_id`. Optional `status`
(`active`, `revoked`, `all`), `limit` (1-100) and `cursor` (up to 512 characters)
are forwarded only when supplied. Omission uses backend defaults; null is not a
query value. Cursors are opaque: retain and return them unchanged with the same
scope and filters. Workstream validates cursor syntax and current authority on
every call; these grant cursors are not cryptographically bound to query scope.
Administrative projections exclude contact details and
external identity subjects; read calls may still update admission/audit state.

## Deployment Boundary

Build from this directory only:

```bash
docker build -t workstream-mcp-foundation:local .
```

The image contains the adapter and its locked dependencies, not the backend.
Configure a fixed trusted `WORKSTREAM_API_URL`, exact allowed Host values and
listener settings. Non-loopback API destinations require HTTPS. Put public
ingress behind HTTPS, with rate limits and matching body, header, connection
and timeout bounds. Preserve `Cache-Control: no-store` on successes and failures;
disable authenticated response caching and redact Authorization and business
payloads in proxy telemetry. Do not expose the container directly as a public
HTTP service. Browser-origin requests are rejected by this native-client profile.

The adapter disables redirects, environment proxy inheritance and automatic
retries. A profile-update transport failure, upstream 5xx response, or unexpected
success/redirect response is reported as non-retryable uncertain execution;
the adapter does not retry the unkeyed mutation. Connections may be pooled, but
caller credentials and results are not shared or cached. Response validation is
pinned to the nine selected public contracts in `contracts/`; upstream drift
must be reviewed, not silently accepted. There is no fallback service or
backend-private import.

## Verification

```bash
uv run --frozen ruff check workstream_mcp tests
uv run --frozen mypy workstream_mcp
uv run --frozen pytest -q --ignore=tests/integration
uv build
```

Real API tests require the repository's isolated PostgreSQL runner, controlled
fixture identities and a separate installed adapter process. Never supply a
production database or real user token to a test. Integration and container
commands are recorded in the additive MCP workflow and the
[current chunk record](../.commitrail/initiatives/WS-MCP-002/WS-MCP-002-03.md).
Selected schemas are compared with the running backend OpenAPI operations;
custom admission, lifecycle and exact-project semantics are exercised separately.

Local fixture evidence does not certify the deployed Flow provider, a public
gateway or all MCP clients. The remaining 18 mapped tools belong to later
bounded changes in the [initiative](../.commitrail/initiatives/WS-MCP-002/OVERVIEW.md).
