# Discovery: WS-MCP-001 - Workstream Contributor MCP Server

## Current branch and base

- Branch: `oxvictor/ws-mcp-001-01-contributor-mcp-foundation`
- Latest inspected upstream main: `f18b620`
- Fork remote: `fork https://github.com/ChuloWay/workstream.git`

## Available backend API surface

Current FastAPI routers expose:

- auth and actor profile routes;
- authorization routes;
- project, guide, setup, and policy routes;
- task lifecycle, task context, submission, and audit routes;
- pre-submit checker and checker-run routes.

Current backend APIs can support MCP task-by-id, locked task context,
submission requirements, pre-submit check, submission listing, and checker-run
reads. The MCP uses only those compatible calls.

The current task claim route leaves work in `claimed` while WS-MCP-001 exposes
one task-claim operation and cannot expose the separate start route. The current
task release route is operator-scoped, not contributor-scoped. Submission
creation does not provide the durable request-idempotency contract required by
the MCP. The HTTP gateway must fail closed for all three until compatible
contributor APIs exist.

## Missing backend API surface for WS-MCP-001

No backend route currently exposes:

- contributor project list for `workstream://me/projects`;
- contributor task list for `workstream://tasks` or
  `workstream://projects/{project_id}/tasks`;
- contribution record reads;
- current review, review context, review claim, review release, or review
  decision APIs.

Additionally, no current backend API provides an atomic contributor
claim-to-work transition, contributor task release, or durable request replay
for submission creation.

The maintainer approved using a simple temporary service layer for unavailable
APIs so MCP tool and resource shape can be implemented and tested now.

## WS-MCP-001 baseline findings

The maintainer-provided PDF is the approved public-behavior baseline. It
requires exactly seven resource types, seven tools, zero prompts, no queue or
event/subscription surface, the same logical surface over STDIO and Streamable
HTTP, current Workstream authorization on every operation, and retry-safe
mutations.

Sections 18 and 20 make conformance and acceptance conditional on evidence that
is broader than this foundation chunk. Current gaps include:

- authoritative production completion of both contributor journeys;
- Submitter, Reviewer, Both, and revoked-access behavior through the MCP boundary;
- initial submission, revision, identical-revision, and all Task Status outcomes;
- concurrent task/review claims against current Workstream truth;
- end-to-end equivalence over both STDIO and Streamable HTTP;
- an MCP Inspector/client capture of discovery and both journeys.

The in-memory scenario gateway and MCP client test exercise stable shapes and
happy paths while APIs are missing. They are not evidence that the production
server has passed the complete WS-MCP-001 conformance or acceptance gate.

## Repo process findings

No `CONTRIBUTING.md`, Husky directory, commitlint config, or package manifest is
present. The active contribution standard is defined by `AGENTS.md`,
`.github/pull_request_template.md`, `.agent-loop/policies/`, and CI gates.

Every PR must add exactly one schema-v2 merge intent under
`.agent-loop/merge-intents/`.

## Design constraints

- Workstream APIs and auth remain authoritative.
- MCP tool inputs must never carry bearer tokens.
- STDIO diagnostics must not write secrets to stdout.
- The temporary service must not become production truth.
