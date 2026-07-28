# Chunk Contract: WS-AUTH-001-11C1 - Project Setup Diagnostic Read Cutover

## Status

Proposed and inactive after 11B. Requires a separate signed explicit start.

## Goal

Hard-cut the six setup and draft diagnostic GET surfaces assigned by AUTH-11
to scoped local administrative grants as the sole product-authority source.

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
.agent-loop/merge-intents/WS-AUTH-001-11C1.json
```

## Not allowed

```text
project or policy mutation
project identity, actor-context, effective-policy, or active-guide routes
contributor access to setup diagnostics
token-role fallback or dual authorization
```

## Acceptance criteria

- Activate exactly the six 11C1 actions listed in the parent contract.
- Canonical project and child-resource ownership are resolved before disclosure;
  unauthorized, nonexistent, and cross-project resources share the action-aware
  concealed public response.
- Same-project cross-guide identifiers and report/policy identifiers bound to a
  different guide are denied with that same concealed response.
- Setup/sufficiency actions require `PROJECT_SETUP_DIAGNOSTIC_READ`; policy
  and checker-setup actions require `PROJECT_EFFECTIVE_POLICY_READ`. Covered
  Project Manager and Audit Authority grants and system Operator grants allow
  their read-only projections. Finance Authority, Access Administrator, and
  contributor grants deny. No read permission implies a mutation permission.
- ProjectRepository remains persistence owner and returns domain records; the
  application layer composes authorization context without a parallel project
  repository in AUTH.
- Every migrated route declares exactly one primary action and uses local
  grants as its sole product-authority source.
- Per-action scope, child-binding, concealed-denial, audit, invalidation, and
  live API contract tests pass, including positive Project Manager/Operator/
  Audit and negative Finance/Access Administrator/contributor cases.
- Authorization spec, role matrix, project operating manual, and authorization
  operations docs match the six action mappings, read-only projections,
  concealment behavior, and removal of token-role authority.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_projects.py --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/test_agent_gates.py
git diff --check
```

Hosted `Backend / test` is mandatory before merge and must preserve the full
semantic lanes, API E2E, repository-wide 78 percent floor, and applicable
authorization subsystem 90 percent floor. New project-read branches require
focused behavior coverage; the pre-existing broad project subsystem remains
under the repository-wide floor until its dedicated coverage uplift.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Stop conditions

Stop if a diagnostic surface cannot be concealed without changing its mutation
lifecycle or if any route would retain token-role authority.
