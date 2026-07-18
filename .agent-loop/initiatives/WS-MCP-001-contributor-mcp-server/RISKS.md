# Risks: WS-MCP-001 - Workstream Contributor MCP Server

| Risk | Severity | Mitigation |
|---|---:|---|
| MCP accidentally becomes a second workflow engine | High | Keep handlers thin and route behavior through `ContributorGateway`; no direct database access. |
| Temporary review/contribution service leaks into production use | High | Make scenario gateway opt-in and label it temporary in code, tests, and docs. |
| Tokens appear in tool inputs, resource URIs, logs, or results | High | Centralize token context and add redaction/token-safety tests. |
| MCP catalogue expands beyond WS-MCP-001 v0.1 | Medium | Test exact resource/tool names and zero prompts. |
| Backend unavailable APIs force schema churn later | Medium | Keep stable MCP schemas and replace only gateway methods when APIs land. |
| Existing lifecycle routes have incompatible actor scope, state transitions, or idempotency | High | Fail closed in the production HTTP gateway; use a test-injected scenario fixture only for foundation contract testing until compatible APIs land. |
| Streamable HTTP is exposed to an untrusted browser origin | High | Use FastMCP transport-security host/origin allowlists and disable SSE transport. |
| Temporary happy-path tests are mistaken for full WS-MCP-001 conformance | High | State explicitly that Sections 18 and 20 remain open until authoritative APIs, both transports, role/revocation cases, concurrency, retries, and the Inspector/client demonstration are proven. |
