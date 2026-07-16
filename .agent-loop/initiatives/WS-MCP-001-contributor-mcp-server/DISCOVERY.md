# Discovery: WS-MCP-001 - Workstream Contributor MCP Server

## Current branch and base

- Branch: `oxvictor/ws-mcp-001-01-contributor-mcp-foundation`
- Latest inspected upstream main: `9a04434`
- Fork remote: `fork https://github.com/ChuloWay/workstream.git`

## Available backend API surface

Current FastAPI routers expose:

- auth and actor profile routes;
- authorization routes;
- project, guide, setup, and policy routes;
- task lifecycle, task context, submission, and audit routes;
- pre-submit checker and checker-run routes.

Current backend APIs can support MCP Submitter operations for task-by-id,
locked task context, submission requirements, task claim, task release,
pre-submit check, submission creation, submission listing, and checker-run
reads.

## Missing backend API surface for WS-MCP-001

No backend route currently exposes:

- contributor project list for `workstream://me/projects`;
- contributor task list for `workstream://tasks` or
  `workstream://projects/{project_id}/tasks`;
- contribution record reads;
- current review, review context, review claim, review release, or review
  decision APIs.

The maintainer approved using a simple temporary service layer for unavailable
APIs so MCP tool and resource shape can be implemented and tested now.

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
