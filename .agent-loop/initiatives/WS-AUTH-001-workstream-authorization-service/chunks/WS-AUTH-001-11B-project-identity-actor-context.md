# Chunk Contract: WS-AUTH-001-11B - Project Identity And Actor Context Cutover

## Status

Proposed and inactive after 11A. Requires a separate signed explicit start.

## Goal

Hard-cut project identity reads to local grants and add a self authorization-
context query that reports only the caller's effective authority for one
canonical project.

## Risk and SLA

L1 / P1

## Allowed files

```text
backend/app/modules/projects/**
backend/app/api/routes/auth.py
backend/app/api/router.py
backend/app/modules/actors/**
backend/app/modules/authorization/**
backend/app/modules/audit/**
backend/tests/test_projects.py
backend/tests/test_auth.py
backend/tests/test_authorization.py
backend/scripts/api_contract_e2e.py
.github/workflows/backend.yml
docs/operations_authorization_service.md
docs/operations_roles_permissions.md
docs/operations_project_operating_manual.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-11B.json
```

## Not allowed

```text
project mutation or setup/policy/guide routes
token-role fallback or dual authorization
grant mutation
project collection/list API
```

## Acceptance criteria

- Activate only `project.read` and `actor.authorization_context.read`.
- Resolve the canonical project before authorization; unknown, cross-project,
  unauthorized, inactive-grant, and out-of-scope requests are concealed by the
  action-aware public denial contract.
- Eligible scoped admin grants receive the registered project identity view.
  Active exact-project submitter, reviewer, and adjudicator grants independently
  receive only the minimal project identity projection.
- The context response is self-only, exact-project, derived from current local
  grants and action availability, and cannot advertise planned/inactive actions.
- Routers declare one primary ActionId and target; policy stays in the kernel or
  feature policy layer. Both routes use local grants as their sole product-
  authority source after cutover.
- Exact-project allow, cross-project deny, role revocation independence,
  minimal-field, concealed-not-found, audit, invalidation, and live API tests
  pass.
- Authorization spec, role matrix, project operating manual, and authorization
  operations docs describe the new context route/schema, project projections,
  concealed denial, and hard removal of token-role authority.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_auth.py tests/test_projects.py --cov=app.modules.authorization --cov=app.modules.actors --cov=app.modules.projects --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/test_agent_gates.py
git diff --check
```

Hosted `Backend / test` is mandatory before merge and must preserve the full
semantic lanes, API E2E, repository-wide 78 percent floor, and applicable
actor/authorization subsystem 90 percent floors. This child adds a protected
`app/modules/projects/*` 90 percent coverage report to that hosted gate.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Stop conditions

Stop if safe context derivation requires exposing raw grants or if either route
would retain token-role authority.
