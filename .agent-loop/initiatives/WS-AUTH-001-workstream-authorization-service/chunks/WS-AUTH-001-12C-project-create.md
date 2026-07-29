# Chunk Contract: WS-AUTH-001-12C — Project Creation Cutover

## Status and prerequisite

Proposed and inactive after 12B.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Activate only `project.create` for a system-scoped Project Manager and remove
token-role authority from project-shell creation.

## Why this chunk exists

Project creation has system scope and cannot share the resource/lock semantics
of mutations against an existing project.

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/projects/models.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/router.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/api/deps/authorization.py
backend/alembic/versions/<then-current-next>_project_create_authority.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

Guide/policy/setup/activation mutations, project update/archive invention,
project-scoped create authority, or token-role fallback.

## Acceptance criteria

- Only an active human with an active identity link and effective system-scoped
  Project Manager `project.create` grant may create a project.
- Project-scoped Project Manager, all contributor grants, and every other admin
  role deny.
- PREP binds actor/link, system grant, request digest, idempotency key, root
  transaction, and server-created project identity; evidence and project commit
  atomically once.
- Replay, copied/wrong handle, revoked authority, wrong session/transaction,
  and duplicate idempotency produce at most one project.
- The route declares exactly one active ActionId and contains no legacy coarse
  role-claim authorization helper.
- New project rows record local actor profile, identity link, matched grant,
  system scope, action, and decision-event reference; historical rows remain
  readable and are not rewritten.
- Every changed authorization/project module remains at least 90 percent
  covered. Final pushed head SHA passes `Backend / test` and `Agent Gates`.

## Verification commands

Before start, freeze exact isolated-runner, migration round-trip, coverage,
Ruff, API drill, stale-doc, link, and diff commands.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

System scope, creation idempotency, transaction ownership, and denial matrix.

## Stop conditions

Stop if project identity cannot be server-owned or project-scoped authority can
create a project.
