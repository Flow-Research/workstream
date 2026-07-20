# Internal Review Evidence

## Chunk

`WS-MCP-001-01`

## Required Statements

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 098285b32c07dbccf1f00447af1f70e06df91306

Reviewed at: 2026-07-20T22:01:23Z

Reviewer run IDs: 019f7cca-7065-7fc3-a102-100773738da9, 019f7cca-7137-7471-a6c9-87703eb97476, 019f7cca-71c0-7301-8f89-f54e37ae8f96, 019f7cca-72d3-7da0-9447-f01a0a08b2f8, 019f7cca-73d2-74e0-ada5-91b8f8c75fc3, 019f7cca-758c-7871-9c3f-8a5a1d28fa83, 019f7ccc-9823-7552-9941-0e5747ba8640, 019f7ccc-98e7-7021-9da3-a5cb3d343db8, 019f7ccc-998c-7420-bed8-92bee8378219

After the reviewed SHA, only review evidence, PR trust-bundle, and status files changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | none | Exact-head review found no actionable engineering issue; unavailable authoritative APIs and full conformance evidence remain bounded follow-up work. |
| QA/test | PASS WITH LOW RISKS | none | 113 MCP tests prove the catalogue, auth wiring, review lifecycle, safe errors, strict gateway outcomes, connection reuse, and Streamable HTTP response lifecycle at 95.27 percent package coverage. |
| security/auth | PASS WITH LOW RISKS | none | Exact UUID-equivalent redaction, actor isolation, fail-closed authority, and distinct retryable Auth outage handling are covered; direct 429/5xx verifier branch tests remain a low risk. |
| product/ops | PASS AFTER FIXES | none | Revision context identifies the reviewed submission and revised work returns to review while the foundation remains truthful about unavailable APIs. |
| architecture | PASS WITH LOW RISKS | none | Production remains a thin API adapter with no direct database access, MCP-owned sessions, or scenario runtime configuration. |
| CI integrity | PASS WITH LOW RISKS | none | MCP CI is isolated in `mcp.yml` with least-privilege permissions and a two-decimal 90 percent coverage gate; current `main` at `61bc039` is fully integrated and all local gates pass. |
| docs | PASS WITH LOW RISKS | none | Operator and initiative records accurately distinguish foundation readiness from complete Sections 18 and 20 acceptance; composed task reads cannot guarantee a cross-request snapshot until an authoritative aggregate API exists. |
| reuse/dedup | PASS | none | Stable-reference validation, metadata bounds, error mapping, observability, replay input, and actor keys remain centralized. |
| test delta | PASS WITH LOW RISKS | none | 112 tests cover the remediation set; direct 429/5xx verifier branches remain a low risk while network-outage and protocol-level 503 behavior are covered. |

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
- CodeRabbit's eleven findings were addressed with least-privilege MCP CI, strict 90 percent coverage, complete recursive redaction, minimal completed-review output, replay ordering/telemetry, revision propagation, reachable path errors, secure issuer configuration, bounded inputs, and bounded constant-space ASGI replay.
- Streamable HTTP now verifies bearer tokens through existing Workstream Auth before creating request context and cannot consume the STDIO process token.
- HTTP bearer forwarding ignores environment proxies. Anonymous streams reach immediate `401`; authenticated request bodies are capped by bytes, frames, and receive time before MCP JSON parsing.
- Bounded replay delegates to the original ASGI receiver after the coalesced body, preserving real disconnect delivery and the Streamable HTTP SSE response lifecycle.
- Revision context records the reviewed submission reference/version, and a revised submission creates the next deterministic review offer in the test-only scenario.
- An MCP operator README documents install, validation, STDIO, secure Streamable HTTP, local-only insecure issuer override, allowlists, API timeout, body byte/frame/deadline caps, and scenario isolation.
- Current upstream `main` at `61bc039` is integrated as `098285b`. The updated backend workflow protects an exact four-job topology, so the unchanged MCP job moved to dedicated `mcp.yml`; both workflow YAML files parse and all repository gates pass.
- The refreshed task APIs still separate claim from start, retain operator release semantics, and lack durable submission replay; contributor list, contribution, and review APIs remain unavailable, so the MCP's fail-closed production boundaries remain correct.
- All seven tools now publish authoritative titles, usage boundaries, parameter guidance, examples, constraints, and typed output schemas through the actual FastMCP registrations.
- Tool execution failures publish MCP errors while a coherent completed checker failure remains a valid negative business outcome.
- `sse-starlette` is declared directly as a development dependency because the protocol journey suite imports it.
- SDK parameter-validation errors are sanitized before reaching clients, including when an invalid value equals the active bearer token.
- Pre-submit checker responses require strict JSON scalar types, a non-authoritative completed status, coherent eligibility, and a matching task identifier; malformed responses fail closed.
- Review claims require a stable review identifier and the exact derived `workstream://reviews/{review_ref}/context` resource before publishing success.
- Output-schema failures remain safe `unexpected_server_error` results rather than being relabeled as input failures, and operation telemetry records the same infrastructure-error outcome.
- UUID bearer equivalents are matched from the parsed secret itself, so compact forms remain detectable even when embedded at an overlapping offset inside a longer hexadecimal run.
- Workstream Auth network, throttling, and server failures now produce a secret-safe retryable HTTP `503`, while rejected credentials remain `401`.
- Invalid authoritative task locked-context responses no longer masquerade as submission errors.
- The operator README now documents a collision-free local HTTP topology, the `/mcp` endpoint, and every production surface that intentionally fails closed.
- Composed Task Context and Task Status reads now reuse and close one `httpx.AsyncClient` per gateway operation, preserving connection pooling without creating long-lived credential state.

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
| STDIO and Streamable HTTP equivalence | Shared registration plus in-memory and real HTTP SDK journeys | Partial; broader end-to-end outcome matrix remains |
| Inspector/client demonstration | In-memory MCP SDK client test | Partial; Inspector capture remains |

## Commands Run

```bash
(cd mcp_server && /tmp/workstream-mcp-validation/bin/python -m ruff check .)
(cd mcp_server && /tmp/workstream-mcp-validation/bin/python -m pytest -q --cov=workstream_mcp --cov-report=term-missing --cov-fail-under=90 --cov-precision=2)
/tmp/workstream-backend-validation/bin/python scripts/check_stale_workstream_wording.py
/tmp/workstream-backend-validation/bin/python scripts/check_markdown_links.py
/tmp/workstream-backend-validation/bin/python scripts/check_stale_authorization_docs.py
/tmp/workstream-backend-validation/bin/python scripts/check_stale_artifact_contracts.py
/tmp/workstream-backend-validation/bin/python scripts/test_agent_gates.py
git diff --check
(cd backend && /tmp/workstream-backend-validation/bin/python -m ruff check app tests scripts)
(cd backend && /tmp/workstream-backend-validation/bin/python -m pytest -q tests/test_api_contract_e2e.py)
```

## Result Summary

```text
MCP tests: 113 passed at 95.27 percent statement coverage.
MCP ruff: passed.
Stale wording: passed.
Markdown links: passed for 11 changed Markdown files.
Stale authorization docs: passed.
Stale artifact contracts: passed.
Agent gate regression: 88 tests passed.
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
- Task Context and Task Status compose multiple authoritative reads and cannot provide cross-request snapshot consistency until Workstream exposes an aggregate API.
- Workstream Auth network-outage and HTTP 503 behavior are directly covered; dedicated 429/5xx verifier branch cases remain a low test risk.
