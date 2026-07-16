# Plan: WS-MCP-001 - Workstream Contributor MCP Server

## Proposed approach

Create a separate Python MCP server package in this repository. Keep the public
MCP catalogue closed to the approved WS-MCP-001 v0.1 surface and route all
available product behavior through the existing Workstream HTTP API.

Unavailable review, contribution, and contributor-list reads are represented by
a temporary scenario gateway that is explicit, deterministic, and replaceable.

## Design chosen

- `workstream_mcp.server` owns MCP registration.
- `workstream_mcp.gateway` defines the contributor gateway interface.
- `workstream_mcp.http_gateway` calls real Workstream HTTP APIs.
- `workstream_mcp.scenario_gateway` supplies temporary deterministic behavior
  only where APIs are unavailable.
- `workstream_mcp.auth` owns token propagation and redaction helpers.
- `workstream_mcp.schemas` owns stable resource/tool metadata and request
  shapes.
- CI runs the MCP package lint and tests in a separate workflow job.

## Alternatives considered

### Direct database access

Rejected because MCP must not bypass Workstream authorization or lifecycle
services.

### Generic `call_api` MCP tool

Rejected because WS-MCP-001 requires a closed contributor-facing catalogue with
stable tool names and schemas.

### Blocking until review and contribution APIs exist

Rejected because the maintainer approved a temporary service layer to avoid
blocking current MCP work.

## Boundaries preserved

- Auth/session: the same issuer bearer token is forwarded to Workstream.
- Permission/policy: Workstream authorization remains authoritative.
- Payment/execution: MCP does not calculate contribution, compensation, or
  payment state.
- Persistence/data: MCP adds no database or durable business state.
- Presentation/API: no frontend work.
- CI/deployment: no workflow or gate weakening.
- CI/deployment: additive MCP checks only; no existing workflow or gate
  weakening.

## Rollout/migration strategy

Land the MCP package as an additive contributor adapter. When Workstream adds
review, contribution, and list APIs, replace temporary scenario-gateway methods
with real HTTP gateway calls without changing the MCP public catalogue.

## Verification strategy

Use focused MCP unit tests for catalogue closure, token safety, HTTP API path
mapping, Submitter flow behavior, temporary review/contribution behavior, and
safe error envelopes. Run repository gate scripts before PR.

## Review strategy

Required reviewers: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta.

## Sequencing

`WS-MCP-001-01` installs the contributor MCP foundation. Later chunks may replace
temporary service methods with real review and contribution API calls after
those backend APIs land.
