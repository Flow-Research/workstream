# PR Trust Bundle

## Chunk

`WS-MCP-001-01` - `Contributor MCP Foundation`

Merge intent: `.agent-loop/merge-intents/WS-MCP-001-01.json`

## Goal

Add the WS-MCP-001 contributor MCP foundation without duplicating Workstream
authority or exposing backend lifecycle endpoints with incompatible contributor
semantics. This PR does not claim that the complete Sections 18 and 20 gate is
closed.

## What Changed

- Added seven WS-MCP-001 resource types, seven tools, and zero prompts.
- Restricted the production HTTP gateway to semantically compatible backend APIs.
- Made contributor `claim_task`, `release_task`, and `submit_task` fail closed until atomic claim-to-work, contributor release, and durable idempotency APIs exist.
- Kept the bounded temporary scenario gateway test-injected only; it is not selectable by runtime configuration.
- Enforced UUID request IDs and strict submission/review input shapes.
- Added safe upstream JSON/error handling, bearer-safe observability, and Streamable HTTP transport security. SSE is not supported.
- Added authoritative `/api/v1/auth/me` validation before unavailable production surfaces, stable-reference/path hardening, and safe backend error-code preservation.
- Scoped temporary idempotency and leases to the actor and completed the temporary resource representations needed for foundation testing.
- Added a real MCP SDK client test for the Submitter and Reviewer journeys and proved no subscriptions or event-like capability is advertised.

## Why It Changed

The original adapter could use backend endpoints whose lifecycle and authority
semantics did not match the contributor MCP specification. Failing closed is
the only correct MCP-side behavior until Workstream supplies compatible APIs.

## Design Chosen

The MCP is a thin contributor protocol adapter. It forwards the issuer token to
Workstream, validates stable inputs, redacts outputs, logs only safe operation
metadata, and holds no workflow or business state. The scenario fixture exists
only for tests that exercise the public MCP contract while backend APIs are
unavailable or incompatible.

## Scope Control

### Allowed Files Changed

- `.agent-loop/initiatives/WS-MCP-001-contributor-mcp-server/**`
- `mcp_server/**`

### Files Outside Contract

- None

## Product Behavior

- [x] Product behavior changed and is explained here: the MCP advertises the approved catalogue but truthfully returns `workstream_temporarily_unavailable` for surfaces that current backend APIs cannot safely implement.

## Evidence

```text
MCP tests: 44 passed.
MCP ruff: passed.
Stale wording, Markdown, authorization, and artifact-contract checks: passed.
Agent gate regression: 87 passed.
Backend ruff: passed.
Focused backend API contract: 15 passed.
git diff --check: passed.
```

Commands:

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

## Foundation Acceptance Criteria Proof

- [x] Seven resource types, seven tools, zero prompts: `mcp_server/tests/test_catalogue.py`.
- [x] Tokens stay transport/session scoped and are redacted from results and logs: `test_auth.py`, `test_http_gateway.py`, and `test_runtime_safety.py`.
- [x] Only compatible backend paths are called; incompatible lifecycle routes fail closed: `test_http_gateway.py`.
- [x] UUID request IDs and strict schemas are exposed at FastMCP runtime: `test_catalogue.py`.
- [x] Temporary lifecycle/review behavior is replay-safe only under explicit test injection: `test_scenario_gateway.py`.
- [x] Temporary replay and task/review leases are actor-scoped: `test_scenario_gateway.py`.
- [x] One temporary happy path for each journey works through a real MCP client session: `test_protocol_journeys.py`.
- [x] No resource subscriptions, list-change events, experimental channels, or MCP tasks are advertised: `test_catalogue.py`.
- [x] Checker failure remains a valid structured outcome: `test_http_gateway.py`.
- [x] Exactly one schema-v2 merge intent exists: `.agent-loop/merge-intents/WS-MCP-001-01.json`.

## WS-MCP-001 Sections 18 And 20

This foundation does not yet prove complete v0.1 conformance or acceptance.
Authoritative production APIs are still required for project/task lists,
contributions, contributor claim/release/submission, and review operations.
Role/revocation coverage, revision and status outcomes, authoritative
concurrency/retry behavior, end-to-end transport equivalence, and the required
Inspector/client capture remain follow-up evidence.

## Test Delta

Added: `mcp_server/tests/test_protocol_journeys.py`.

Modified: `test_auth.py`, `test_catalogue.py`, `test_http_gateway.py`,
`test_runtime_safety.py`, and `test_scenario_gateway.py`.

## Internal Reviewer Results

Reviewed code SHA: 950afda1b9a1c1a93fd47318f4a08fe0d047cdad

Reviewed at: 2026-07-18T17:34:01Z

Reviewer run IDs: senior-engineering-mcp-spec-alignment-local-review, qa-test-mcp-spec-alignment-local-review, security-auth-mcp-spec-alignment-local-review, product-ops-mcp-spec-alignment-local-review, architecture-mcp-spec-alignment-local-review, ci-integrity-mcp-spec-alignment-local-review, docs-mcp-spec-alignment-local-review, reuse-dedup-mcp-spec-alignment-local-review, test-delta-mcp-spec-alignment-local-review

| Reviewer | Result | Blocking Findings | Notes |
|---|---:|---|---|
| Senior engineering | PASS | none | Lifecycle routes are fail-closed when they cannot meet the MCP contract. |
| QA/test | PASS WITH LOW RISKS | none | 44 focused MCP foundation tests pass; remaining Section 18 cases are recorded. |
| Security/auth | PASS | none | Token, transport, path, actor-ownership, and safe-error boundaries are covered. |
| Product/ops | PASS WITH LOW RISKS | none | Unavailable outcomes are truthful pending backend work; full v0.1 acceptance is not claimed. |
| Architecture | PASS | none | No backend or persistence ownership moved into MCP. |
| CI integrity | PASS | none | No gate weakening. |
| Docs | PASS AFTER FIXES | none | Initiative docs distinguish foundation PR readiness from full specification acceptance. |
| Reuse/dedup | PASS | none | Boundary behavior is centralized. |
| Test delta | PASS WITH LOW RISKS | none | New tests cover temporary protocol happy paths, resource context, replay conflicts, and actor-separated leases; authoritative conformance remains follow-up work. |

## External Review

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Pending | PR not opened yet. |
| GitHub checks | Pending | PR not opened yet. |

## Remaining Risks

- Review, contribution, contributor-list, atomic contributor claim/release, and durable submission-idempotency APIs are still missing.
- This MCP chunk cannot provide those actions in production until compatible backend contracts land.
- Full backend database tests require CI or a configured `WORKSTREAM_TEST_DATABASE_URL`; local focused backend contract tests pass.
- Full WS-MCP-001 acceptance remains open for the authoritative and transport evidence listed above.

## Follow-Up Work

Replace test-only scenario methods with real HTTP gateway calls when the required
backend API contracts land.

## Human Review Focus

Inspect the fail-closed lifecycle boundaries, token/redaction behavior,
Streamable HTTP allowlists, and the distinction between production gateway and
test-only scenario fixture.

## Human Merge Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
