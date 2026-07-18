# Internal Review Evidence

## Chunk

`WS-MCP-001-01`

## Required Statements

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: c4be9750d1cc123b7f98371f83fa0696946679e6

Reviewed at: 2026-07-18T14:24:26Z

Reviewer run IDs: senior-engineering-mcp-final-local-review, qa-test-mcp-final-local-review, security-auth-mcp-final-local-review, product-ops-mcp-final-local-review, architecture-mcp-final-local-review, ci-integrity-mcp-final-local-review, docs-mcp-final-local-review, reuse-dedup-mcp-final-local-review, test-delta-mcp-final-local-review

After the reviewed SHA, only review evidence, PR trust-bundle, and status files changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | none | The adapter is current with upstream and preserves Workstream lifecycle authority while validating stable references and unavailable-surface identity. |
| QA/test | PASS | none | Forty-four MCP tests cover the closed catalogue, real MCP protocol journeys, fail-closed production behavior, replay conflicts, and actor-separated leases. |
| security/auth | PASS | none | Existing Workstream Auth validates tokens before unavailable responses; token syntax, path references, transport configuration, redaction, and actor ownership fail closed. |
| product/ops | PASS WITH LOW RISKS | none | The MCP has a truthful unavailable result until compatible backend APIs exist instead of exposing an incorrect contributor action. |
| architecture | PASS | none | Production remains a thin API adapter with no direct database access or scenario runtime configuration. |
| CI integrity | PASS | none | No CI or gate behavior changed or weakened; focused MCP lint/tests, 87 agent gates, and the focused backend API contract pass. Full database tests require the unavailable `WORKSTREAM_TEST_DATABASE_URL`. |
| docs | PASS AFTER FIXES | none | Initiative discovery, plan, risk, status, and contract record the backend capability boundary accurately. |
| reuse/dedup | PASS | none | Stable-reference validation, error mapping, observability, canonical replay input, and actor keys remain centralized. |
| test delta | PASS | none | Tests exercise the corrected production behavior, complete temporary representations, actor-scoped replay/leases, and both journeys through an MCP SDK client. |

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
- Unavailable production surfaces now validate the bearer through `/api/v1/auth/me` before returning their truthful unavailable result.
- Stable task, project, review, and routing references reject path traversal and unsafe path characters before any downstream request.
- Known safe Workstream authorization and domain error codes are preserved instead of collapsing every `403` into one category.
- Runtime configuration rejects remote plaintext API URLs, credential-bearing URLs, non-positive/non-finite timeouts, and empty HTTP allowlists.
- The temporary fixture scopes idempotency and task/review leases to the actor without storing or returning raw bearer tokens.
- Temporary resource representations now include the locked task context, status outcomes/actions, compensation context, lease timing, checker context, and revision context required for v0.1 conformance.
- The runtime explicitly proves no resource subscriptions, list-change notifications, experimental channels, or MCP tasks are advertised.
- A real in-memory MCP SDK client completes the Submitter and Reviewer journeys over the registered protocol surface.

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
(cd backend && /tmp/workstream-backend-venv/bin/python -m ruff check app tests scripts)
(cd backend && /tmp/workstream-backend-venv/bin/python -m pytest -q tests/test_api_contract_e2e.py)
```

## Result Summary

```text
MCP tests: 44 passed.
MCP ruff: passed.
Stale wording: passed.
Markdown links: passed for 10 changed Markdown files.
Stale authorization docs: passed.
Stale artifact contracts: passed.
Agent gate regression: 87 tests passed.
Backend ruff: passed.
Focused backend API contract: 15 passed.
git diff --check: passed.
```

The full backend suite was also attempted in an isolated environment. It reached
789 passing tests, but database-backed tests could not run because
`WORKSTREAM_TEST_DATABASE_URL` is not configured locally; the resulting 111
failures and 429 setup errors are outside the MCP diff.

## Remaining Risks

- Current main still lacks review, contribution, contributor project-list, and contributor task-list APIs.
- Current claim, release, and submission routes cannot meet WS-MCP-001's contributor lifecycle or durable-idempotency contract. Production returns a structured unavailable outcome for those MCP surfaces until compatible APIs land.
- The temporary scenario gateway is a test fixture only. It must never be configured as production behavior.
- Full backend database evidence remains delegated to CI or a local PostgreSQL environment with `WORKSTREAM_TEST_DATABASE_URL` configured.
