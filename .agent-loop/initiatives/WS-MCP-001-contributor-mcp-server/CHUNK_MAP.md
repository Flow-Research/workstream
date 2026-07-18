# Chunk Map: WS-MCP-001 - Workstream Contributor MCP Server

## Rule

Only one chunk may be active at a time. Do not begin a follow-up MCP chunk until
the current chunk is implemented, verified, reviewed, merged by explicit human
approval, recorded by merge-memory automation, and stopped.

## Chunks

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| `WS-MCP-001-01` | Contributor MCP Foundation | L1 | Ready for PR |
| `WS-MCP-001-02` | Replace Temporary Gateway And Close Conformance | L1 | Proposed after backend APIs exist |

## Dependency order

```text
WS-MCP-001-01
-> WS-MCP-001-02
```

`WS-MCP-001-02` covers authoritative project/task lists, contributions,
contributor claim/release/submission, review resources/tools, and the remaining
Sections 18 and 20 evidence. It is not limited to review and contribution APIs.

## Stop condition

After `WS-MCP-001-01` merges and automated merge memory records it, stop. Do not
start `WS-MCP-001-02` without a separate explicit start signal and available
backend API contracts.
