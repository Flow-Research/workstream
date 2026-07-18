# Internal Review Evidence

## Chunk

`WS-MCP-001-01`

## Required Statements

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 4438f4ac9375485b409cf2a7f944e179e6f6421b

Reviewed at: 2026-07-18T17:37:04Z

Reviewer run IDs: senior-engineering-mcp-tool-annotation-local-review, qa-test-mcp-tool-annotation-local-review, security-auth-mcp-tool-annotation-local-review, product-ops-mcp-tool-annotation-local-review, architecture-mcp-tool-annotation-local-review, ci-integrity-mcp-tool-annotation-local-review, docs-mcp-tool-annotation-local-review, reuse-dedup-mcp-tool-annotation-local-review, test-delta-mcp-tool-annotation-local-review

After the reviewed SHA, only review evidence, PR trust-bundle, and status files changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | none | The adapter is current with upstream and preserves Workstream lifecycle authority while validating stable references and unavailable-surface identity. |
| QA/test | PASS WITH LOW RISKS | none | Forty-four MCP tests cover the foundation catalogue, temporary happy paths, fail-closed production behavior, replay conflicts, and actor-separated leases; they do not close every Section 18 case. |
| security/auth | PASS | none | Existing Workstream Auth validates tokens before unavailable responses; token syntax, path references, transport configuration, redaction, and actor ownership fail closed. |
| product/ops | PASS WITH LOW RISKS | none | The foundation has truthful unavailable results until compatible backend APIs exist and does not claim full v0.1 acceptance. |
| architecture | PASS | none | Production remains a thin API adapter with no direct database access or scenario runtime configuration. |
| CI integrity | PASS | none | No CI or gate behavior changed or weakened; focused MCP lint/tests, 87 agent gates, and the focused backend API contract pass. Full database tests require the unavailable `WORKSTREAM_TEST_DATABASE_URL`. |
| docs | PASS AFTER FIXES | none | Initiative records now distinguish foundation readiness from the complete Sections 18 and 20 conformance and acceptance gates. |
| reuse/dedup | PASS | none | Stable-reference validation, error mapping, observability, canonical replay input, and actor keys remain centralized. |
| test delta | PASS WITH LOW RISKS | none | Tests exercise corrected production behavior, temporary representations, actor-scoped replay/leases, and one temporary happy path per journey through an MCP SDK client; remaining conformance cases are explicit follow-up work. |

## Valid Findings Addressed

- The legacy task claim route leaves work in `claimed`, while MCP `claim_task` cannot expose a separate start transition. The production gateway now fails closed until Workstream provides an atomic contributor claim-to-work API.
- The legacy task release route releases a screened task and requires operator authority. It is no longer exposed through contributor `release_task`.
- Legacy submission creation does not supply durable request replay. The production gateway now fails closed for `submit_task` until that contract exists.
- Runtime scenario mode was removed. The temporary scenario gateway must be injected explicitly by tests and cannot be selected by environment configuration.
- Request IDs are UUIDs, matching current backend header validation.
- Streamable HTTP now uses FastMCP DNS-rebinding host/origin allowlists, allows only secure loopback defaults unless configured, and rejects unsupported SSE transport.
- Non-JSON upstream success bodies and unexpected handler failures now become safe MCP errors without stack traces or secret leakage.
- Tool input schemas are precise for submission packets, review findings, decisions, and UUID request IDs; `needs_revision` requires findings before the gateway call.
- The scenario fixture now implements replay-safe task/review lifecycle behavior solely for foundation contract tests.
- Secret-safe operation metadata is logged without bearer tokens or request bodies.
- Unavailable production surfaces now validate the bearer through `/api/v1/auth/me` before returning their truthful unavailable result.
- Stable task, project, review, and routing references reject path traversal and unsafe path characters before any downstream request.
- Known safe Workstream authorization and domain error codes are preserved instead of collapsing every `403` into one category.
- Runtime configuration rejects remote plaintext API URLs, credential-bearing URLs, non-positive/non-finite timeouts, and empty HTTP allowlists.
- The temporary fixture scopes idempotency and task/review leases to the actor without storing or returning raw bearer tokens.
- Temporary resource representations now include the locked task context, status outcomes/actions, compensation context, lease timing, checker context, and revision context needed to exercise the v0.1 foundation shapes.
- The runtime explicitly proves no resource subscriptions, list-change notifications, experimental channels, or MCP tasks are advertised.
- A real in-memory MCP SDK client exercises one temporary Submitter happy path and one temporary Reviewer happy path over the registered protocol surface.
- `run_pre_submit_check` is published as read-only and non-destructive; the six lifecycle tools are published as state-changing. All seven tools publish their retry-safe idempotency hint.

## WS-MCP-001 Specification Status

The reviewed PDF is the approved public-behavior baseline. This PR proves the
closed catalogue and foundation boundaries, but does not claim complete
Sections 18 and 20 conformance or acceptance.

| Specification area | Foundation evidence | Status |
|---|---|---:|
| Catalogue and zero prompts/subscriptions | Exact registration and capability tests | Proven |
| Identity transport and token secrecy | Forwarding, redaction, invalid-token, and schema tests | Partially proven; production role/revocation matrix remains |
| Submitter and Reviewer journeys | Temporary in-memory happy paths | Partial; authoritative APIs and remaining lifecycle cases are unavailable |
| Retry and concurrency | Temporary actor-scoped replay/conflict tests | Partial; authoritative concurrent outcomes remain |
| STDIO and Streamable HTTP equivalence | Shared registration and HTTP security configuration | Open end-to-end |
| Inspector/client demonstration | In-memory MCP SDK client test | Partial; Inspector capture remains |

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
- Full WS-MCP-001 Sections 18 and 20 acceptance remains open until authoritative APIs and the recorded transport, role/revocation, lifecycle, retry/concurrency, and Inspector evidence exist.
