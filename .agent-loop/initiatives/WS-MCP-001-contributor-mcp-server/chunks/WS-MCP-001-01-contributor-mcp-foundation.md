# Chunk Contract: WS-MCP-001-01 - Contributor MCP Foundation

## Parent initiative

`WS-MCP-001` - Workstream Contributor MCP Server

## Goal

Add the first contributor-facing MCP server package with the closed WS-MCP-001
resource and tool catalogue, real HTTP gateway calls for currently available
Workstream APIs, and a temporary scenario gateway for unavailable review,
contribution, contributor-list, task-list, and incompatible lifecycle surfaces.

## Why this chunk exists

This lets contributor MCP work begin without waiting for later backend
contributor-list, lifecycle, review, and contribution APIs while preserving
Workstream as the authority.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-MCP-001-contributor-mcp-server/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-MCP-001-contributor-mcp-server/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-MCP-001-contributor-mcp-server/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
.agent-loop/initiatives/WS-MCP-001-contributor-mcp-server/**
.agent-loop/merge-intents/WS-MCP-001-01.json
.github/workflows/backend.yml
mcp_server/**
scripts/check_internal_review_evidence.py
scripts/test_agent_gates.py
```

## Not allowed

```text
backend/app/**
backend/alembic/**
other `.github/workflows/**`
other `scripts/**`
frontend/**
direct database access
admin/operator/project-manager MCP tools
MCP prompts
production reliance on temporary review/contribution data
CI or gate weakening
```

## Acceptance criteria

- [ ] The MCP package exposes exactly the approved v0.1 resource types and tool names.
- [ ] No prompts are exposed.
- [ ] Workstream bearer tokens are transport/session context, never tool inputs or resource URI values.
- [ ] HTTP gateway maps only semantically compatible Submitter APIs to current `/api/v1` endpoints and fails closed otherwise.
- [ ] Temporary scenario gateway covers unavailable review, contribution, contributor-list, and incompatible lifecycle surfaces in tests only.
- [ ] `claim_task` does not invoke `start_task`.
- [ ] Pre-submit checker failures are returned as valid structured outcomes.
- [ ] Tests cover catalogue closure, auth forwarding, Submitter behavior, temporary reviewer/contribution behavior, and token redaction.
- [ ] CI runs MCP server lint and tests.
- [ ] Internal review evidence gate treats `mcp_server/` changes as review-relevant.
- [ ] Exactly one schema-v2 merge intent is added.

## WS-MCP-001 acceptance boundary

These are acceptance criteria for the foundation chunk, not the complete
WS-MCP-001 Sections 18 and 20 gate. The foundation may merge with production
surfaces failing closed, but full v0.1 acceptance still requires authoritative
end-to-end journeys, role/revocation behavior, revision and status cases,
concurrency and retry evidence, equivalent STDIO and Streamable HTTP behavior,
and the required Inspector/client demonstration.

## Verification commands

```bash
(cd mcp_server && python -m pytest -q)
(cd mcp_server && python -m ruff check .)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
git diff --check
(cd backend && ruff check app tests scripts)
(cd backend && pytest -q tests/test_api_contract_e2e.py)
```

## Required reviewers

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] CI integrity
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

Confirm the MCP catalogue stays closed, the temporary service layer is visibly
non-authoritative, and bearer-token handling cannot leak secrets into MCP
schemas, resource URIs, stdout, logs, or results.

## Stop conditions

Stop and escalate if:

- the MCP catalogue needs to expand beyond WS-MCP-001 v0.1;
- backend API implementation becomes required to finish this MCP-only chunk;
- any unavailable contributor-list, task-list, lifecycle, review, or
  contribution API is treated as production-ready through scenario data;
- auth or idempotency behavior needs product-service changes;
- CI/test weakening is required to pass;
- secrets or production data are needed.
