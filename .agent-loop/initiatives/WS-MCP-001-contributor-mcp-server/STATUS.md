# Status: WS-MCP-001 - Workstream Contributor MCP Server

## Current status

`WS-MCP-001-01` received a final MCP-scope review against current upstream and
is ready for PR on branch `oxvictor/ws-mcp-001-01-contributor-mcp-foundation`.

## Active implementation chunk

`WS-MCP-001-01` - Contributor MCP Foundation.

## Current implementation branch

`oxvictor/ws-mcp-001-01-contributor-mcp-foundation`

## Chunk status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-MCP-001-01` | Ready for PR | `oxvictor/ws-mcp-001-01-contributor-mcp-foundation` | - | Production gateway fails closed for incompatible backend lifecycle routes; auth, actor ownership, replay, path safety, and protocol journeys have current evidence at `c4be975`. |
| `WS-MCP-001-02` | Proposed | - | - | Replace temporary service methods after review/contribution APIs exist. |

## Blockers

Production completion is blocked on compatible Workstream APIs. Review,
contribution, and contributor-list APIs are unavailable on current main; the
current task claim, release, and submission routes also do not meet the MCP's
actor, lifecycle, or durable-idempotency contract. The production HTTP gateway
returns a structured unavailable result for those surfaces. The bounded
scenario gateway is test-injected only and is not a production fallback.
