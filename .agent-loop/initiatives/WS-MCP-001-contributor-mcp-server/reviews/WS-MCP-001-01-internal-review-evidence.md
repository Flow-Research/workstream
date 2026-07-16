# Internal Review Evidence

## Chunk

`WS-MCP-001-01`

## Required Statements

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 6573bc30e054372d1391cb6f472462a8e83b6981

Reviewed at: 2026-07-16T15:59:17Z

Reviewer run IDs: senior-engineering-final-local-review, qa-test-final-local-review, security-auth-final-local-review, product-ops-final-local-review, architecture-final-local-review, ci-integrity-final-local-review, docs-final-local-review, reuse-dedup-final-local-review, test-delta-final-local-review

After the reviewed SHA, only evidence and status files changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | none | Whitespace-only resource IDs fixed with non-blank validators; entrypoint, validation, and backend mappings accepted. |
| QA/test | PASS | none | Invalid input-shape tests and runtime FastMCP input-schema assertions added; MCP tests reached 18 passing. |
| security/auth | PASS WITH LOW RISKS | none | Bearer token repr, forwarding, and output redaction accepted; future hardening can make STDIO fallback more explicit. |
| product/ops | PASS WITH LOW RISKS | none | Default HTTP mode fails closed for unavailable APIs; scenario mode is explicit. |
| architecture | PASS WITH LOW RISKS | none | Boundaries and gateway split accepted; no backend/domain imports or DB access. |
| CI integrity | PASS AFTER FIXES | none | MCP CI job, merge-intent null successor, and `mcp_server/` review-gate relevance added. |
| docs | PASS AFTER FIXES | none | Evidence file added; initiative docs cover temporary, auth, no-DB, and CI boundaries. |
| reuse/dedup | PASS WITH LOW RISKS | none | Shared MCP concerns are centralized; runtime registration duplication is covered by tests. |
| test delta | PASS | none | New tests cover catalogue, auth, HTTP paths, validation failures, scenario flow, and pre-submit failure behavior. |

## Valid Findings Addressed

- Temporary scenario gateway defaulted into runtime HTTP mode. Fixed by making the default HTTP gateway fail closed for unavailable backend APIs and requiring explicit scenario injection or `WORKSTREAM_MCP_GATEWAY_MODE=scenario`.
- Tool schemas were defined but not enforced. Fixed by validating each tool input through the Pydantic schemas and adding negative tests for invalid decisions, blank identifiers, non-dict submissions, and malformed findings.
- MCP server had no runnable entrypoint. Fixed with `workstream-mcp-server` console script and `python -m workstream_mcp`.
- Bearer token could appear in `RequestContext` repr and echoed gateway outputs. Fixed with `repr=False` and redaction on all tool/resource results.
- Runtime FastMCP registration was not tested against the closed catalogue. Fixed with runtime resource/tool/prompt and input-schema assertions.
- Scenario fixture used wall-clock time. Fixed with a stable scenario timestamp.
- `mcp_server/` was outside CI and review-gate scope. Fixed with an additive MCP CI job and internal review gate coverage.
- Merge intent referenced an undeclared successor chunk. Fixed by setting successor fields to `null`.

## Commands Run

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

## Result Summary

```text
MCP tests: 18 passed.
MCP ruff: passed.
Stale wording: passed.
Markdown links: passed for changed Markdown files.
Stale authorization docs: passed.
Stale artifact contracts: passed.
Agent gate regression: 71 tests passed.
Backend ruff: passed.
Backend API contract e2e: 14 passed.
git diff --check: passed.
Backend full pytest: attempted, but local shell lacks WORKSTREAM_TEST_ADMIN_DATABASE_URL / WORKSTREAM_TEST_DATABASE_URL for the database-backed suite.
```

## Remaining Risks

- Review, contribution, contributor project-list, and contributor task-list backend APIs are still unavailable. The MCP default runtime fails closed for those surfaces; the temporary scenario gateway is explicit and non-authoritative.
- Full backend pytest requires a local Postgres admin DSN through `WORKSTREAM_TEST_ADMIN_DATABASE_URL`; CI owns that complete isolated database run.
