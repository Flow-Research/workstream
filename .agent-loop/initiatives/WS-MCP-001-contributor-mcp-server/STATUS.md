# Status: WS-MCP-001 - Workstream Contributor MCP Server

## Current status

`WS-MCP-001-01` addressed all current maintainer and CodeRabbit MCP-scope
findings and received final review results at reconciled head `785336e`.
It is open as
[PR #149](https://github.com/Flow-Research/workstream/pull/149)
from branch
`oxvictor/ws-mcp-001-01-contributor-mcp-foundation`.

This status means the foundation chunk is PR-ready. It does not mean the full
WS-MCP-001 Sections 18 and 20 conformance and acceptance gates are complete.

## Active implementation chunk

`WS-MCP-001-01` - Contributor MCP Foundation.

## Current implementation branch

`oxvictor/ws-mcp-001-01-contributor-mcp-foundation`

## Chunk status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-MCP-001-01` | Final review ready to push | `oxvictor/ws-mcp-001-01-contributor-mcp-foundation` | [#149](https://github.com/Flow-Research/workstream/pull/149) | Current `main` at `42a89b2` is integrated as `785336e` without MCP-file changes; 112 MCP tests pass at 95.25 percent coverage. External re-review and checks remain pending after push. |
| `WS-MCP-001-02` | Proposed | - | - | Replace every temporary method with authoritative APIs and close the remaining Sections 18 and 20 evidence. |

## Blockers

Production completion is blocked on compatible Workstream APIs. Review,
contribution, and contributor-list APIs are unavailable on current main; the
current task claim, release, and submission routes also do not meet the MCP's
actor, lifecycle, or durable-idempotency contract. The production HTTP gateway
returns a structured unavailable result for those surfaces. The bounded
scenario gateway is test-injected only and is not a production fallback.

Full WS-MCP-001 acceptance also remains blocked on authoritative role and
revocation cases, initial/revision/status outcomes, concurrent retry behavior,
STDIO/Streamable HTTP equivalence, and the required Inspector/client
demonstration.
