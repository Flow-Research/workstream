# Chunk Contract: WS-AUTH-001-11C2 - Effective Policy And Active Guide Read Cutover

## Status

Proposed and inactive after 11C1. Requires a separate signed explicit start.

## Goal

Hard-cut effective artifact policy, pre-submit checker policy, and active-guide
reads to local authority with explicit principal-specific disclosure.

## Risk and SLA

L1 / P1

## Allowed files

```text
backend/app/modules/projects/**
backend/app/modules/authorization/**
backend/app/modules/audit/**
backend/tests/test_projects.py
backend/tests/test_authorization.py
backend/scripts/api_contract_e2e.py
.github/workflows/backend.yml
docs/operations_authorization_service.md
docs/operations_roles_permissions.md
docs/operations_project_operating_manual.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-11C2.json
```

## Not allowed

```text
project, guide, source, or policy mutation
setup diagnostic or actor-context routes
raw payment or internal diagnostic disclosure to contributors
token-role fallback or dual authorization
```

## Acceptance criteria

- Activate exactly the three 11C2 actions listed in the parent contract.
- Effective policy actions require `PROJECT_EFFECTIVE_POLICY_READ`; covered
  Project Manager/Audit grants and system Operator grants receive only their
  read projections, while Finance and Access Administrator grants deny.
  Active-guide access requires `PROJECT_READ` plus its principal-specific
  projection. Any contributor access to active-guide content requires an explicit
  response schema that omits payment, provenance, draft setup, and internal
  diagnostic fields; absence of such a proven schema means contributors deny.
- Effective policy queries cannot reveal draft or cross-project configuration.
- Same-project cross-guide identifiers are denied with the same concealed
  response as unauthorized and nonexistent resources.
- Canonical project resolution and authorization precede sensitive assembly;
  concealed denial is identical for unauthorized and nonexistent resources.
- Every migrated route declares exactly one primary action and uses local
  grants as its sole product-authority source.
- Principal-specific field allowlists, scope, concealed denial, audit,
  invalidation, and live API contract tests pass.
- Authorization spec, role matrix, project operating manual, and authorization
  operations docs match effective-policy and active-guide schemas, principal
  projections, concealment, and removal of token-role authority.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_projects.py --cov=app.modules.authorization --cov=app.modules.projects --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/test_agent_gates.py
git diff --check
```

Hosted `Backend / test` is mandatory before merge and must preserve the full
semantic lanes, API E2E, repository-wide 78 percent floor, and applicable
authorization subsystem 90 percent floor. The protected
`app/modules/projects/*` 90 percent report introduced by 11B remains mandatory.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Stop conditions

Stop if contributor-safe projection cannot be proven or if cutover requires a
mutation, compatibility response, or token-role authority.
