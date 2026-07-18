# Internal Review Evidence

## Chunk

`WS-MCP-001-01`

## Required Statements

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: aaff8a1400b530946e6e57a11ad2e0e753543219

Reviewed at: 2026-07-18T13:46:15Z

Reviewer run IDs: senior-engineering-mcp-remediation-local-review, qa-test-mcp-remediation-local-review, security-auth-mcp-remediation-local-review, product-ops-mcp-remediation-local-review, architecture-mcp-remediation-local-review, ci-integrity-mcp-remediation-local-review, docs-mcp-remediation-local-review, reuse-dedup-mcp-remediation-local-review, test-delta-mcp-remediation-local-review

After the reviewed SHA, only review evidence, PR trust-bundle, and status files changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | none | The HTTP gateway no longer maps a contributor tool to a route with incompatible lifecycle semantics. |
| QA/test | PASS | none | Added coverage for fail-closed lifecycle surfaces, scenario replay behavior, safe malformed upstream responses, runtime policy, and observability. MCP tests reached 26 passing. |
| security/auth | PASS | none | UUID request identifiers match current backend middleware; bearer data is absent from schemas, results, repr, and operation logs. Streamable HTTP has host/origin protection and SSE is rejected. |
| product/ops | PASS WITH LOW RISKS | none | The MCP has a truthful unavailable result until compatible backend APIs exist instead of exposing an incorrect contributor action. |
| architecture | PASS | none | Production remains a thin API adapter with no direct database access or scenario runtime configuration. |
| CI integrity | PASS | none | No CI or gate behavior changed or weakened; focused MCP lint/tests and repository gates pass. |
| docs | PASS AFTER FIXES | none | Initiative discovery, plan, risk, status, and contract record the backend capability boundary accurately. |
| reuse/dedup | PASS | none | Error envelopes, observability, validation, and scenario replay handling remain centralized. |
| test delta | PASS | none | Tests exercise the corrected production behavior and the test-injected fixture's complete lifecycle/idempotency behavior. |

## Valid Findings Addressed

- The legacy task claim route leaves work in `claimed`, while MCP `claim_task` cannot expose a separate start transition. The production gateway now fails closed until Workstream provides an atomic contributor claim-to-work API.
- The legacy task release route releases a screened task and requires operator authority. It is no longer exposed through contributor `release_task`.
- Legacy submission creation does not supply durable request replay. The production gateway now fails closed for `submit_task` until that contract exists.
- Runtime scenario mode was removed. The temporary scenario gateway must be injected explicitly by tests and cannot be selected by environment configuration.
- Request IDs are UUIDs, matching current backend header validation.
- Streamable HTTP now uses FastMCP DNS-rebinding host/origin allowlists, allows only secure loopback defaults unless configured, and rejects unsupported SSE transport.
- Non-JSON upstream success bodies and unexpected handler failures now become safe MCP errors without stack traces or secret leakage.
- Tool input schemas are precise for submission packets, review findings, decisions, and UUID request IDs; `needs_revision` requires findings before the gateway call.
- The scenario fixture now implements replay-safe task/review lifecycle behavior solely for conformance tests.
- Secret-safe operation metadata is logged without bearer tokens or request bodies.

## Commands Run

```bash
(cd mcp_server && /tmp/workstream-mcp-venv/bin/python -m ruff check .)
(cd mcp_server && /tmp/workstream-mcp-venv/bin/python -m pytest -q)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
git diff --check
```

## Result Summary

```text
MCP tests: 26 passed.
MCP ruff: passed.
Stale wording: passed.
Markdown links: passed for 10 changed Markdown files.
Stale authorization docs: passed.
Stale artifact contracts: passed.
Agent gate regression: 71 tests passed.
git diff --check: passed.
```

## Remaining Risks

- Current main still lacks review, contribution, contributor project-list, and contributor task-list APIs.
- Current claim, release, and submission routes cannot meet WS-MCP-001's contributor lifecycle or durable-idempotency contract. Production returns a structured unavailable outcome for those MCP surfaces until compatible APIs land.
- The temporary scenario gateway is a test fixture only. It must never be configured as production behavior.
