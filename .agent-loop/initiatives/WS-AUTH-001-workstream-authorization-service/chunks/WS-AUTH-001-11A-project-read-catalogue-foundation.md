# Chunk Contract: WS-AUTH-001-11A - Project Read Catalogue And Projection Foundation

## Status

Active for implementation. Signed automation run `30191914627` activated this
exact child on protected main `bd2203d5`. Chat and local branch state are not
authority; the signed automation projection is the canonical start proof.

## Goal

Register the eleven AUTH-11 actions as planned and establish typed projection
contracts without activating any API route.

## Risk and SLA

L1 / P1

## Allowed files

```text
backend/app/modules/authorization/**
backend/app/modules/audit/**
backend/alembic/versions/0035_project_read_action_evidence.py
backend/tests/test_authorization.py
backend/tests/test_auth.py
backend/tests/test_alembic.py
backend/tests/conftest.py
docs/operations_authorization_service.md
docs/operations_roles_permissions.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-11A.json
```

## Not allowed

```text
backend/app/modules/projects/**
backend/app/modules/actors/router.py
route activation or token-role changes
compatibility aliases or fallback paths
```

## Acceptance criteria

- Register exactly the eleven actions enumerated by parent AUTH-11, initially
  unavailable and owned by 11B, 11C1, or 11C2 as assigned there.
- Add exactly `PROJECT_SETUP_DIAGNOSTIC_READ` and
  `PROJECT_EFFECTIVE_POLICY_READ`. Grant both to Project Manager, Operator, and
  Audit Authority under their existing compatible scopes; do not grant them to
  Finance Authority, Access Administrator, or contributor roles.
- Map project identity and active guide to existing `PROJECT_READ`, setup and
  sufficiency diagnostics to `PROJECT_SETUP_DIAGNOSTIC_READ`, draft/effective
  policy reads to `PROJECT_EFFECTIVE_POLICY_READ`, and actor context to the
  existing self-profile read permission.
- Define only AUTH-owned action/resource-context contracts here. Product
  response projections remain with their owning 11B/11C application layers.
- Migration `0035` adds the two typed/PostgreSQL permissions, exact role
  mappings, and action-evidence parity and proves upgrade from `0034`,
  downgrade, re-upgrade, and fresh replay.
- Typed and PostgreSQL matrix tests prove both permissions for Project Manager,
  system Operator, and covered Audit Authority, and prove their absence for
  Finance Authority, Access Administrator, and all contributor roles.
- Generated action/permission/owner parity tests pass and no route becomes
  available.
- Authorization spec and operations/role documentation describe both new
  permissions, exact role/scope mappings, planned action owners, and continued
  unavailability.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_alembic.py --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic upgrade head)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic downgrade -1)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic upgrade head)
python3 scripts/test_agent_gates.py
git diff --check
```

Hosted `Backend / test` is mandatory before merge and must preserve the full
semantic lanes, API E2E, repository-wide 78 percent floor, and applicable
authorization subsystem 90 percent floor.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Stop conditions

Stop if registration requires route activation, any permission beyond the two
explicitly named read permissions, or edits to historical migrations.
