# Workstream MCP Profile Foundation

An independently installed adapter exposing one tool:
`workstream_profile_get`. It calls the public Workstream
`GET /api/v1/actors/me` operation with the caller's bearer. There are no MCP
resources, prompts, mutations or administrative tools in this package.

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

Tool arguments are exactly `{}`. The result contains the authorized full
self-profile response; first admission can create the actor/link and update
admission timestamps, but does not grant roles. Suspended self-read and
deactivated/revoked-link denial follow Workstream. Errors are MCP tool failures
with safe status/code information, not fabricated profiles.

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
retries. Connections may be pooled, but caller credentials and profile results
are not shared or cached. Response validation is pinned to the selected public
contract in `contracts/profile_get.json`; upstream drift must be reviewed, not
silently accepted. There is no fallback service or backend-private import.

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
[first-chunk record](../.commitrail/initiatives/WS-MCP-002/WS-MCP-002-01.md).
The selected schema is compared with the running backend's OpenAPI operation;
custom admission and lifecycle semantics are exercised separately.

Local fixture evidence does not certify the deployed Flow provider, a public
gateway or all MCP clients. The remaining 26 mapped tools belong to later
bounded changes in the [initiative](../.commitrail/initiatives/WS-MCP-002/OVERVIEW.md).
