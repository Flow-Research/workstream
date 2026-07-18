# Chunk Contract: WS-AUTH-001-12 - Project Policy And Setup Mutation Cutover

## Status

Proposed and inactive. Exact ActionIds and migration `0028` mapping/provenance
delta must be enumerated before implementation; AUTH-PREP is required.

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Move project creation, guide/source mutation, policy derivation/approval,
activation, and repair operations to local scoped permissions and matched-grant
provenance.

## Why this chunk exists

This completes project authorization required before separately starting
`WS-POL-002-04`; it does not claim ownership of PR #90 or implement that later
runtime-hardening chunk.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/projects/**
backend/app/modules/authorization/**
backend/app/api/deps/auth.py
backend/app/workers/project_setup.py
backend/alembic/versions/0028_*.py
backend/tests/test_projects.py
backend/tests/test_auth.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-12.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
WS-POL-002-03 post-submit approval/visibility behavior
task/submission/checker authorization
review or compensation behavior
unscoped project-manager access or token role fallback
```

## Acceptance criteria

- System-scoped Project Manager can create projects; scoped managers mutate
  only covered projects.
- Submitter, reviewer, or adjudicator grants never substitute for Project
  Manager authority, separately or together. Admin roles do not gain project
  mutation outside their defined system/scoped permissions.
- Project policy actions use registered permissions and transaction-local grant
  revalidation.
- Project-guide source ingestion behavior and resource facts remain owned by
  `WS-ART-001-03`; this chunk neither activates its artifact action nor grants
  direct provider access. The dedicated AUTH custodian activates it only after
  hidden ART behavior merges.
- Every migrated project mutation and setup command declares one primary
  registered action and authorizes against `system`, an existing project, or the
  exact existing parent policy resource defined by the owning project model.
  It does not collapse guide, source-snapshot, submission-policy, checker-policy,
  review-policy, or revision-policy records into an invented generic policy
  resource. Contribution policy resources are independently owned by WS-CON
  and are outside this project-mutation cutover.
- Generated OpenAPI/command manifest-delta tests prove every protected project
  mutation/setup surface migrated here has exactly one active `ActionId`
  declaration.
- Approval provenance records matched local grant/actor/scope while preserving
  historical bootstrap provenance.
- Migration `0028` adds exact action-evidence parity plus matched local
  grant/scope provenance and ownership
  constraints to project policy approval records without rewriting historical
  bootstrap values; prior-head upgrade, downgrade, and re-upgrade preserve
  readable history.
- Internal setup worker uses explicit system permission and current context.
- Every sensitive mutation consumes AUTH-PREP after locking and recomposing
  final project facts. State, idempotency, audit, and invalidation effects remain
  atomic under one route/service-command commit.
- No project mutation uses `require_any_role()` or token roles.
- Full backend suite and API contract drill pass.

## Verification commands

```bash
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic upgrade head)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic downgrade -1)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic upgrade head)
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q \
  tests/test_authorization.py tests/test_auth.py tests/test_projects.py \
  --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Review project scope, transaction-time authority, approval provenance, system
worker behavior, and strict exclusion of WS-POL product changes.

## Stop conditions

Stop if project scope cannot be derived canonically, post-submit approval
behavior must change, wrong project roles must substitute for management, or a
mutation would bypass AUTH-PREP.
