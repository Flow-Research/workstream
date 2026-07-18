# Internal Review Evidence

## Chunk

`WS-MCP-001-01`

## Required Statements

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: a9504ea9fe4c70fa021bd9e306aa0e8b26372a10

Reviewed at: 2026-07-18T19:20:59Z

Reviewer run IDs: 019f7672-e843-73b0-9edb-76302cf14d44, 019f7672-ea4f-73e2-8c9f-43c0d58b4782, 019f7672-ed1c-7f23-8016-6a882188d692, 019f7672-ef20-75d0-b1a4-88d080b3aac4, 019f7672-f15a-78d0-8de7-ec38941649ed, 019f7687-e4f2-7210-ad56-5d261ed41cdf, 019f7688-3446-7651-818c-7e9dc7d24a6f, 019f7688-3879-72f0-8a2a-e15b572a93f2

After the reviewed SHA, only review evidence, PR trust-bundle, and status files changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | none | Input limits, lifecycle propagation, replay ordering, and error boundaries were repaired without moving authority into MCP. |
| QA/test | PASS AFTER FIXES | none | Seventy-six MCP tests prove the external findings, auth wiring, revision loop, safe errors, and a strict 93.71 percent package coverage result. |
| security/auth | PASS AFTER FIXES | none | Workstream Auth verifies HTTP tokens; transport credentials are isolated; proxy inheritance is disabled; body/input limits and redaction fail closed. |
| product/ops | PASS AFTER FIXES | none | Revision context identifies the reviewed submission and revised work returns to review while the foundation remains truthful about unavailable APIs. |
| architecture | PASS AFTER FIXES | none | Production remains a thin API adapter with no direct database access, MCP-owned sessions, or scenario runtime configuration. |
| CI integrity | PASS AFTER FIXES | none | MCP CI has least-privilege permissions and enforces 90 percent coverage at two-decimal precision; all local gates pass. |
| docs | PASS AFTER FIXES | none | Initiative records now distinguish foundation readiness from the complete Sections 18 and 20 conformance and acceptance gates. |
| reuse/dedup | PASS AFTER FIXES | none | Stable-reference validation, metadata bounds, error mapping, observability, replay input, and actor keys remain centralized. |
| test delta | PASS AFTER FIXES | none | Tests now cover every CodeRabbit finding and internal follow-up; remaining authoritative Section 18 cases are explicit follow-up work. |

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
- The PR branch was refreshed from upstream `f18b620`; the intervening changes are unrelated review-lifecycle planning records and introduce no MCP conflict.
- CodeRabbit's ten findings were addressed with least-privilege MCP CI, strict 90 percent coverage, complete recursive redaction, minimal completed-review output, replay ordering/telemetry, revision propagation, reachable path errors, secure issuer configuration, and bounded input shapes.
- Streamable HTTP now verifies bearer tokens through existing Workstream Auth before creating request context and cannot consume the STDIO process token.
- HTTP bearer forwarding ignores environment proxies and request bodies are capped before MCP JSON parsing.
- Revision context records the reviewed submission reference/version, and a revised submission creates the next deterministic review offer in the test-only scenario.
- An MCP operator README documents install, validation, STDIO, secure Streamable HTTP, local-only insecure issuer override, allowlists, timeout, body cap, and scenario isolation.

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
(cd mcp_server && /tmp/workstream-mcp-validation/bin/python -m ruff check .)
(cd mcp_server && /tmp/workstream-mcp-validation/bin/python -m pytest -q --cov=workstream_mcp --cov-report=term-missing --cov-fail-under=90 --cov-precision=2)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
git diff --check
(cd backend && /tmp/workstream-backend-validation/bin/python -m ruff check app tests scripts)
(cd backend && /tmp/workstream-backend-validation/bin/python -m pytest -q tests/test_api_contract_e2e.py)
```

## Result Summary

```text
MCP tests: 76 passed at 93.71 percent statement coverage.
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
