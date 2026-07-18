# Workstream Contributor MCP Server

This package is the contributor-facing WS-MCP-001 adapter. Workstream remains
the lifecycle and authorization authority; the MCP server forwards bearer
tokens to the existing Workstream APIs and does not own login sessions or read
the database directly.

## Install And Validate

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest -q --cov=workstream_mcp --cov-report=term-missing \
  --cov-fail-under=90 --cov-precision=2
```

## STDIO

STDIO is the default transport. Supply the actor token through the process
environment; it is never an MCP tool argument.

```bash
WORKSTREAM_API_BASE_URL=http://127.0.0.1:8000 \
WORKSTREAM_MCP_ISSUER_TOKEN='<external-token>' \
.venv/bin/workstream-mcp-server
```

## Streamable HTTP

Streamable HTTP requires an explicit external issuer URL. Production issuer and
Workstream API URLs must use HTTPS. The server verifies each presented token
through Workstream's existing `/api/v1/auth/me` service before creating MCP
request context.

```bash
WORKSTREAM_MCP_TRANSPORT=streamable-http \
WORKSTREAM_API_BASE_URL=https://workstream.example.com \
WORKSTREAM_MCP_AUTH_ISSUER_URL=https://identity.example.com \
WORKSTREAM_MCP_ALLOWED_HOSTS=mcp.example.com \
WORKSTREAM_MCP_ALLOWED_ORIGINS=https://app.example.com \
.venv/bin/workstream-mcp-server
```

Local HTTP issuer development must be deliberate and loopback-only:

```bash
WORKSTREAM_MCP_TRANSPORT=streamable-http \
WORKSTREAM_API_BASE_URL=http://127.0.0.1:8000 \
WORKSTREAM_MCP_AUTH_ISSUER_URL=http://127.0.0.1:8000 \
WORKSTREAM_MCP_ALLOW_INSECURE_AUTH_ISSUER=true \
.venv/bin/workstream-mcp-server
```

`WORKSTREAM_MCP_REQUEST_TIMEOUT_SECONDS` controls Workstream API timeouts.
`WORKSTREAM_MCP_ALLOWED_HOSTS` and `WORKSTREAM_MCP_ALLOWED_ORIGINS` are
comma-separated allowlists. After authentication, HTTP request bodies are
capped at 2 MiB, 1,024 ASGI frames, and 30 seconds of body-receive time. Proxy
environment variables are intentionally ignored for bearer-token forwarding.

The `ScenarioContributorGateway` is a deterministic test fixture only. Runtime
configuration cannot select it.
