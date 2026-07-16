# PR Trust Bundle

## Chunk

`WS-MCP-001-01` - `Contributor MCP Foundation`

Merge intent: `.agent-loop/merge-intents/WS-MCP-001-01.json`

## Goal

Add the first Workstream contributor MCP server package with a closed v0.1 catalogue, real HTTP calls for currently available task/submission/checker APIs, and explicit temporary scenario coverage for unavailable APIs.

## Human-Approved Intent

- Intent: `.agent-loop/initiatives/WS-MCP-001-contributor-mcp-server/INTENT.md`
- Chunk contract: `.agent-loop/initiatives/WS-MCP-001-contributor-mcp-server/chunks/WS-MCP-001-01-contributor-mcp-foundation.md`

## What Changed

- Added `mcp_server/` Python package using `mcp>=1.27,<2`.
- Added seven WS-MCP-001 resource types, seven tools, and zero prompts.
- Added HTTP gateway calls for available Workstream task/submission/checker APIs.
- Added explicit scenario gateway for unavailable review/contribution/list APIs.
- Added MCP lint/test CI and internal-review gate relevance for `mcp_server/`.

## Why It Changed

The maintainer approved starting MCP work against current APIs while using a simple temporary service layer for missing APIs.

## Design Chosen

Thin MCP handlers validate input, propagate bearer context, redact outputs, and route all product behavior through a contributor gateway. Default HTTP mode fails closed for missing backend APIs; scenario mode is opt-in.

## Alternatives Rejected

- Direct database access: rejected because Workstream APIs and authorization must remain authoritative.
- Generic API proxy tool: rejected because WS-MCP-001 requires a closed contributor catalogue.
- Blocking all work until review/contribution APIs exist: rejected because the maintainer approved a temporary test layer.

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

- [x] Product behavior changed and is explained here: an additive MCP adapter is introduced. Workstream lifecycle authority remains in existing APIs.

## Evidence

### Commands Run

```bash
(cd mcp_server && /opt/homebrew/Caskroom/miniforge/base/bin/python3.12 -m pytest -q)
(cd mcp_server && /opt/homebrew/Caskroom/miniforge/base/bin/python3.12 -m ruff check . --output-format concise)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
(cd backend && /tmp/workstream-backend-venv/bin/python -m ruff check app tests scripts --output-format concise)
(cd backend && /tmp/workstream-backend-venv/bin/python -m pytest -q tests/test_api_contract_e2e.py)
git diff --check
```

### Result Summary

```text
MCP tests: 18 passed.
MCP ruff: passed.
Repo static gates: passed.
Agent gate regression: 71 passed.
Backend ruff: passed.
Backend API contract e2e: 14 passed.
git diff --check: passed.
Database-backed full backend pytest needs WORKSTREAM_TEST_ADMIN_DATABASE_URL and is left to CI/local Postgres runner.
```

## Acceptance Criteria Proof

- [x] Exactly seven resource types and seven tools, zero prompts: `mcp_server/tests/test_catalogue.py`.
- [x] Bearer token is transport/session context, not tool input: `mcp_server/tests/test_auth.py` and runtime input-schema assertions.
- [x] Available Submitter APIs call current `/api/v1` paths: `mcp_server/tests/test_http_gateway.py`.
- [x] Temporary unavailable surfaces are explicit and fail closed by default: `HTTPContributorGateway` tests.
- [x] `claim_task` does not invoke `start_task`: HTTP path test.
- [x] Pre-submit checker failure is a valid structured outcome: pre-submit test.
- [x] Exactly one schema-v2 merge intent added.

## Test Delta

### Tests Added

- `mcp_server/tests/test_auth.py`
- `mcp_server/tests/test_catalogue.py`
- `mcp_server/tests/test_http_gateway.py`
- `mcp_server/tests/test_scenario_gateway.py`
- `scripts/test_agent_gates.py` coverage for `mcp_server/` review relevance.

### Tests Modified

- None existing product tests modified.

### Tests Removed Or Skipped

- None

## Internal Reviewer Results

Reviewed code SHA: 6573bc30e054372d1391cb6f472462a8e83b6981

Reviewed at: 2026-07-16T15:59:17Z

Reviewer run IDs: senior-engineering-final-local-review, qa-test-final-local-review, security-auth-final-local-review, product-ops-final-local-review, architecture-final-local-review, ci-integrity-final-local-review, docs-final-local-review, reuse-dedup-final-local-review, test-delta-final-local-review

| Reviewer | Result | Blocking Findings | Notes |
|---|---:|---|---|
| Senior engineering | PASS | none | Valid findings fixed. |
| QA/test | PASS | none | Valid findings fixed. |
| Security/auth | PASS WITH LOW RISKS | none | Future hardening can make STDIO fallback explicit. |
| Product/ops | PASS WITH LOW RISKS | none | Scenario mode is explicit. |
| Architecture | PASS WITH LOW RISKS | none | Boundaries accepted. |
| CI integrity | PASS AFTER FIXES | none | Evidence file added after reviewed SHA. |
| Docs | PASS AFTER FIXES | none | Evidence file added after reviewed SHA. |
| Reuse/dedup | PASS WITH LOW RISKS | none | Runtime registration duplication is test-guarded. |
| Test delta | PASS | none | MCP tests and CI coverage added. |

## External Review

External review response file:

- `.agent-loop/initiatives/WS-MCP-001-contributor-mcp-server/reviews/WS-MCP-001-01-external-review-response.md`

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Pending | PR not opened yet. |
| GitHub checks | Pending | PR not opened yet. |

## CI And Gate Integrity

- [x] No workflow weakening.
- [x] No lint/test/docstring gate weakening.
- [x] No coverage threshold weakening.
- [x] No package script weakening.
- [x] No unpinned new GitHub Action.
- [x] Checkout credential persistence disabled where checkout is used.

## Remaining Risks

- Missing backend APIs are represented only by fail-closed default behavior and explicit scenario mode.
- Full backend database suite was not run locally because no local Postgres admin DSN is configured.

## Follow-Up Work

Replace scenario gateway methods with real review, contribution, contributor project-list, and contributor task-list APIs when backend endpoints land.

## Human Review Focus

Please inspect bearer-token propagation/redaction, fail-closed missing API behavior, and the additive MCP CI job.

## Human Merge Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
