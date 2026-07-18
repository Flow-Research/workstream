# Plan: WS-MCP-001 - Workstream Contributor MCP Server

## Proposed approach

Create a separate Python MCP server package in this repository. Keep the public
MCP catalogue closed to the approved WS-MCP-001 v0.1 surface and route all
available product behavior through the existing Workstream HTTP API.

Unavailable contributor project/task lists, contributions, review surfaces, and
incompatible contributor lifecycle actions are represented by a temporary
scenario gateway that is explicit, deterministic, test-injected, and
replaceable. The HTTP gateway must fail closed for any existing route whose
actor scope, lifecycle semantics, or idempotency guarantees do not satisfy
WS-MCP-001.

## Design chosen

- `workstream_mcp.server` owns MCP registration.
- `workstream_mcp.gateway` defines the contributor gateway interface.
- `workstream_mcp.http_gateway` calls only semantically compatible Workstream
  HTTP APIs and fails closed for incompatible lifecycle routes.
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
- CI/deployment: additive MCP checks only; no existing workflow or gate
  weakening.

## Specification acceptance boundary

This chunk establishes the closed public catalogue, boundary architecture,
stable schemas, safe production degradation, and temporary protocol fixtures.
It is PR-ready as a foundation chunk, but it is not a claim that WS-MCP-001 v0.1
has passed the complete conformance or acceptance gates in Sections 18 and 20.

Full acceptance remains dependent on authoritative backend APIs and evidence
for role variants and revocation, initial and revised submissions, all status
outcomes, concurrent claims, retry behavior, STDIO/Streamable HTTP equivalence,
and an Inspector/client demonstration.

## Rollout/migration strategy

Land the MCP package as an additive contributor adapter. When Workstream adds
review, contribution, list, atomic contributor claim/release, and durably
idempotent submission APIs, replace temporary scenario-gateway methods with
real HTTP gateway calls without changing the MCP public catalogue.

## Verification strategy

Use focused MCP tests for catalogue closure, token safety, HTTP API path
mapping, temporary Submitter/Reviewer happy paths, actor-scoped leases and
replay, safe error envelopes, protocol registration, and the absence of
subscriptions/events. Run repository gate scripts before PR. Record remaining
WS-MCP-001 conformance cases as follow-up evidence rather than treating the
temporary fixture as production proof.

## Review strategy

Required reviewers: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta.

## Sequencing

`WS-MCP-001-01` installs the contributor MCP foundation. A later explicit chunk
replaces every temporary method with authoritative project/task list,
contribution, contributor lifecycle, and review API calls, then closes the
remaining Sections 18 and 20 evidence.
