# Intent: WS-MCP-001 - Workstream Contributor MCP Server

## Human-level goal

Expose the approved contributor-facing Workstream MCP surface so MCP clients can
help Submitters and Reviewers work through governed Workstream journeys without
duplicating Workstream state, authorization, or lifecycle rules.

## Why now

The maintainer approved starting MCP work against the APIs that exist today and
using a small temporary service layer for required MCP surfaces that are not
yet implemented by the backend.

## Success state

This foundation chunk succeeds when the repository contains a contributor MCP
server package that:

- publishes only the WS-MCP-001 v0.1 resources and tools;
- forwards authenticated contributor requests to Workstream APIs where they
  exist;
- isolates unavailable review, contribution, and task-list surfaces, plus
  lifecycle calls whose current routes cannot meet the MCP contract, behind a
  temporary replaceable test service;
- preserves existing Workstream auth and lifecycle authority.

This chunk does not by itself satisfy the WS-MCP-001 Sections 18 and 20
conformance and acceptance gates. Those gates require authoritative production
journeys and transport, authorization, retry, concurrency, and demonstration
evidence after the missing Workstream APIs exist.

## Non-goals

- No Admin, Operator, Project Manager, Finance, or Audit MCP capabilities.
- No MCP-owned identity, role, grant, session, workflow, queue, review, or
  contribution database.
- No direct database access.
- No frontend implementation.
- No production dependency on the temporary service layer.

## Business/product/engineering context

Workstream is Flow's task evaluation and contribution infrastructure. The MCP
server is a contributor protocol adapter over that infrastructure, not a new
workflow engine.

## Human judgment required

Maintainers must confirm the temporary service layer remains acceptable until
contributor-list, lifecycle, review, and contribution APIs land, and must
explicitly approve the foundation PR for merge. Full WS-MCP-001 acceptance
must not be claimed from test-fixture behavior alone.

## Initial risk class

L1
