# Workstream PR Trust Bundle

This PR body follows `.github/pull_request_template.md` and
`.agent-loop/templates/PR_TRUST_BUNDLE.md`.

## Chunk

`WS-MCP-001-01` - `Contributor MCP Foundation`

Merge intent: `.agent-loop/merge-intents/WS-MCP-001-01.json`

## Goal

Add the WS-MCP-001 contributor MCP foundation without duplicating Workstream
authority or exposing backend lifecycle endpoints with incompatible contributor
semantics. This PR does not claim that the complete Sections 18 and 20 gate is
closed.

## Human-Approved Intent

Link the initiative and chunk contract:

- Intent: `.agent-loop/initiatives/WS-MCP-001-contributor-mcp-server/INTENT.md`
- Chunk contract: `.agent-loop/initiatives/WS-MCP-001-contributor-mcp-server/chunks/WS-MCP-001-01-contributor-mcp-foundation.md`

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
- Published MCP tool annotations that distinguish the read-only pre-submit check from the six state-changing lifecycle tools.
- Addressed CodeRabbit's eleven findings with least-privilege CI, strict 90 percent coverage, complete redaction, revision/replay fixes, secure HTTP auth configuration, bounded inputs, and constant-space ASGI request replay.
- Made Streamable HTTP verify tokens through existing Workstream Auth, isolated HTTP from the STDIO token, disabled bearer proxy inheritance, rejected anonymous streams before body buffering, and capped authenticated bodies by bytes, frames, and receive time.
- Preserved the real ASGI receiver after bounded replay and added a real MCP SDK Streamable HTTP SSE journey.
- Added an MCP operator README and completed the test-only revision-to-review loop with reviewed-submission references.
- Published complete agent-facing descriptions, parameter metadata, examples, constraints, and typed output schemas for all seven tools.
- Added direct `sse-starlette` test dependency ownership and strict MCP error signaling at the official SDK boundary.
- Required strict coherent checker responses and exact validated Review Context references before publishing successful outcomes.
- Kept malformed output-schema failures on the server-error path and aligned their operation telemetry with the client-visible infrastructure error.
- Closed overlapping compact-UUID redaction, Auth-outage classification, locked-context error mapping, and local HTTP operator-documentation gaps found during final review.
- Reused one closed HTTP client per composed task-resource operation after CodeRabbit identified repeated connection setup.

## Why It Changed

The original adapter could use backend endpoints whose lifecycle and authority
semantics did not match the contributor MCP specification. Failing closed is
the only correct MCP-side behavior until Workstream supplies compatible APIs.

## Design Chosen

The MCP is a thin contributor protocol adapter. It forwards the issuer token to
Workstream, validates stable inputs, redacts outputs, logs only safe operation
metadata, verifies HTTP identity through existing Workstream Auth, and holds no workflow or business state. The scenario fixture exists
only for tests that exercise the public MCP contract while backend APIs are
unavailable or incompatible.

## Alternatives Rejected

- Direct database access, because it would bypass Workstream authority.
- A generic API-call tool, because the v0.1 catalogue is closed.
- Mapping contributor tools to backend routes with incompatible actor,
  lifecycle, or idempotency semantics.
- Runtime scenario configuration, because temporary data must never become
  production truth.

## Scope Control

### Allowed Files Changed

- `.agent-loop/initiatives/WS-MCP-001-contributor-mcp-server/**`
- `.agent-loop/merge-intents/WS-MCP-001-01.json`
- `.github/workflows/backend.yml`
- `mcp_server/**`
- `scripts/check_internal_review_evidence.py`
- `scripts/test_agent_gates.py`

### Files Outside Contract

- None

## Product Behavior

- [ ] No Workstream product behavior changed.
- [x] Product behavior changed and is explained here: the MCP advertises the approved catalogue but truthfully returns `workstream_temporarily_unavailable` for surfaces that current backend APIs cannot safely implement.

## Evidence

### Commands Run

```bash
(cd mcp_server && /tmp/workstream-mcp-validation/bin/python -m ruff check .)
(cd mcp_server && /tmp/workstream-mcp-validation/bin/python -m pytest -q --cov=workstream_mcp --cov-report=term-missing --cov-fail-under=90 --cov-precision=2)
/tmp/workstream-backend-validation/bin/python scripts/check_stale_workstream_wording.py
/tmp/workstream-backend-validation/bin/python scripts/check_markdown_links.py
/tmp/workstream-backend-validation/bin/python scripts/check_stale_authorization_docs.py
/tmp/workstream-backend-validation/bin/python scripts/check_stale_artifact_contracts.py
/tmp/workstream-backend-validation/bin/python scripts/test_agent_gates.py
/tmp/workstream-backend-validation/bin/python scripts/check_internal_review_evidence.py
git diff --check
(cd backend && /tmp/workstream-backend-validation/bin/python -m ruff check app tests scripts)
(cd backend && /tmp/workstream-backend-validation/bin/python -m pytest -q tests/test_api_contract_e2e.py)
```

### Result Summary

```text
MCP tests: 113 passed at 95.27 percent statement coverage.
MCP ruff: passed.
Stale wording, Markdown, authorization, and artifact-contract checks: passed.
Agent gate regression: 88 passed.
Backend ruff: passed.
Focused backend API contract: 15 passed.
git diff --check: passed.
```

## Acceptance Criteria Proof

The checked items below prove the foundation chunk criteria, not complete
WS-MCP-001 Sections 18 and 20 acceptance.

- [x] Seven resource types, seven tools, zero prompts: `mcp_server/tests/test_catalogue.py`.
- [x] Tokens stay transport/session scoped and are redacted from results and logs: `test_auth.py`, `test_http_gateway.py`, and `test_runtime_safety.py`.
- [x] Only compatible backend paths are called; incompatible lifecycle routes fail closed: `test_http_gateway.py`.
- [x] UUID request IDs and strict schemas are exposed at FastMCP runtime: `test_catalogue.py`.
- [x] Temporary lifecycle/review behavior is replay-safe only under explicit test injection: `test_scenario_gateway.py`.
- [x] Temporary replay and task/review leases are actor-scoped: `test_scenario_gateway.py`.
- [x] One temporary happy path for each journey works through a real MCP client session: `test_protocol_journeys.py`.
- [x] No resource subscriptions, list-change events, experimental channels, or MCP tasks are advertised: `test_catalogue.py`.
- [x] Tool annotations identify `run_pre_submit_check` as read-only and the six lifecycle tools as state-changing: `test_catalogue.py`.
- [x] Streamable HTTP tokens are verified through existing Workstream Auth and cannot fall back to STDIO credentials: `test_auth.py`, `test_runtime_safety.py`.
- [x] Submission, review, metadata, and authenticated HTTP body bytes, frames, and receive time are bounded before gateway work; anonymous streams reach immediate `401`: `test_catalogue.py`, `test_runtime_safety.py`.
- [x] Bounded request replay preserves real ASGI disconnect delivery and an official SDK client completes Streamable HTTP initialization and `tools/list`: `test_runtime_safety.py`, `test_protocol_journeys.py`.
- [x] `needs_revision` persists findings and reviewed submission version, permits resubmission, and requeues review: `test_scenario_gateway.py`.
- [x] Checker failure remains a valid structured outcome: `test_http_gateway.py`.
- [x] All seven tool contracts publish complete agent guidance and typed input/output schemas through `tools/list`: `test_catalogue.py` and `test_protocol_journeys.py`.
- [x] SDK validation errors cannot echo bearer material into MCP responses or logs: `test_protocol_journeys.py`.
- [x] Malformed checker and review-claim gateway responses fail closed as MCP errors: `test_protocol_journeys.py`.
- [x] Output-schema failures remain server errors and log matching infrastructure-error telemetry: `test_protocol_journeys.py`.
- [x] Exactly one schema-v2 merge intent exists: `.agent-loop/merge-intents/WS-MCP-001-01.json`.

## WS-MCP-001 Sections 18 And 20

This foundation does not yet prove complete v0.1 conformance or acceptance.
Authoritative production APIs are still required for project/task lists,
contributions, contributor claim/release/submission, and review operations.
Role/revocation coverage, revision and status outcomes, authoritative
concurrency/retry behavior, end-to-end transport equivalence, and the required
Inspector/client capture remain follow-up evidence.

## Test Delta

### Tests Added

- `mcp_server/tests/test_auth.py`
- `mcp_server/tests/test_catalogue.py`
- `mcp_server/tests/test_http_gateway.py`
- `mcp_server/tests/test_protocol_journeys.py`
- `mcp_server/tests/test_runtime_safety.py`
- `mcp_server/tests/test_scenario_gateway.py`

### Tests Modified

- `scripts/test_agent_gates.py`

### Tests Removed Or Skipped

- None

## Internal Reviewer Results

Reviewed code SHA: 07b7311e7c19da33774661f11ee384d6ef81849d

Reviewed at: 2026-07-20T07:46:58Z

Reviewer run IDs: 019f7cca-7065-7fc3-a102-100773738da9, 019f7cca-7137-7471-a6c9-87703eb97476, 019f7cca-71c0-7301-8f89-f54e37ae8f96, 019f7cca-72d3-7da0-9447-f01a0a08b2f8, 019f7cca-73d2-74e0-ada5-91b8f8c75fc3, 019f7cca-758c-7871-9c3f-8a5a1d28fa83, 019f7ccc-9823-7552-9941-0e5747ba8640, 019f7ccc-98e7-7021-9da3-a5cb3d343db8, 019f7ccc-998c-7420-bed8-92bee8378219

| Reviewer | Result | Blocking Findings | Notes |
|---|---:|---|---|
| Senior engineering | PASS WITH LOW RISKS | none | No actionable exact-head engineering findings; unavailable authoritative APIs remain explicit follow-up work. |
| QA/test | PASS WITH LOW RISKS | none | 113 tests pass at 95.27 percent coverage, including agent-facing catalogue, composed-client reuse, distinct error boundaries, and real SDK HTTP journeys. |
| Security/auth | PASS WITH LOW RISKS | none | Existing Auth verification, exact bearer-equivalent redaction, actor isolation, and retryable Auth outage handling are covered. |
| Product/ops | PASS AFTER FIXES | none | Revision context and requeue are complete in the fixture; unavailable production outcomes remain truthful. |
| Architecture | PASS WITH LOW RISKS | none | No backend, persistence, or session ownership moved into MCP. |
| CI integrity | PASS WITH LOW RISKS | none | Least privilege and a two-decimal 90 percent coverage gate are enforced; current `main` at `42a89b2` is integrated without changing MCP files. |
| Docs | PASS WITH LOW RISKS | none | Initiative and operator docs are accurate; composed task reads await an authoritative aggregate API for snapshot consistency. |
| Reuse/dedup | PASS | none | Boundary validation, mapping, replay, and observability remain centralized. |
| Test delta | PASS WITH LOW RISKS | none | The remediation set is covered; direct 429/5xx verifier branch cases remain a low test risk. |

## External Review

External review response file:

- `.agent-loop/initiatives/WS-MCP-001-contributor-mcp-server/reviews/WS-MCP-001-01-external-review-response.md`

| Source | Status | Notes |
|---|---:|---|
| Maintainer | Findings addressed locally; confirmation pending | Complete agent-facing tool contracts are implemented and protocol-tested through code head `07b7311`. |
| CodeRabbit | Findings addressed locally; re-review pending | The composed-client reuse nitpick and all earlier findings are addressed through `07b7311`; rerun after push. |
| GitHub checks | Pending | Checks must run against the final branch head after push. |

## CI And Gate Integrity

- [x] No workflow weakening.
- [x] No lint/test/docstring gate weakening.
- [x] No coverage threshold weakening.
- [x] No package script weakening.
- [x] No unpinned new GitHub Action.
- [x] Checkout credential persistence disabled where checkout is used.

## Remaining Risks

- Review, contribution, contributor-list, atomic contributor claim/release, and durable submission-idempotency APIs are still missing.
- This MCP chunk cannot provide those actions in production until compatible backend contracts land.
- Full backend database tests require CI or a configured `WORKSTREAM_TEST_DATABASE_URL`; local focused backend contract tests pass.
- Full WS-MCP-001 acceptance remains open for the authoritative and transport evidence listed above.
- Composed task resources cannot guarantee a cross-request snapshot until an authoritative aggregate API exists.
- Auth network-outage and protocol-level 503 behavior are covered; direct 429/5xx verifier branch cases remain a low test risk.

## Follow-Up Work

Replace every test-only scenario method with real HTTP gateway calls when the
required contributor-list, lifecycle, contribution, and review API contracts
land, then close the remaining Sections 18 and 20 evidence.

## Human Review Focus

Please inspect:

- fail-closed lifecycle boundaries;
- token propagation and redaction behavior;
- stable-reference and actor-lease isolation;
- Streamable HTTP host/origin allowlists;
- the distinction between the production gateway and test-only scenario fixture;
- the explicit boundary between foundation readiness and full v0.1 acceptance.

## Human Merge Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
