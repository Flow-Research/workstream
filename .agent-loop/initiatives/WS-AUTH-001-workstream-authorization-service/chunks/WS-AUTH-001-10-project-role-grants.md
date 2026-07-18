# Chunk Contract: WS-AUTH-001-10 - Project Qualification And Contributor Role Grants

## Status

Proposed and inactive. Before implementation review, this contract must add the
exact ActionId/target/guard inventory required by D27. AUTH-PREP is a hard
runtime prerequisite.

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Implement immutable qualification snapshots and independent
`ProjectRoleGrant(submitter|reviewer|adjudicator)` create, list, and revoke
behavior scoped to the exact project under Project Manager authority.

## Why this chunk exists

Project contributor authority must be durable, explicit, revocable, and
separate from both token claims and administrative roles.

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
backend/app/modules/actors/**
backend/app/modules/authorization/**
backend/app/modules/projects/models.py
backend/app/modules/projects/repository.py
backend/app/api/router.py
backend/app/db/models.py
backend/app/modules/audit/**
backend/alembic/versions/0026_*.py
backend/tests/test_actors.py
backend/tests/test_projects.py
backend/tests/test_auth.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/operations_authorization_service.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-10.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
automated grants from skills or reputation
self-grant or self-revoke of the issuer's own contributor grant through the
administrative project-grant operation
admin roles satisfying submitter/reviewer/adjudicator permissions
task/review lifecycle implementation
project/task/checker authorization cutover
`both`, compatibility alias, replacement event/reason, `replaced_grant_id`, or
silent conversion of combined/replacement evidence
editing migrations `0018`, `0019`, or `0022`
```

## Acceptance criteria

- Snapshot is immutable, actor/project/requested-role-bound, privacy-bounded,
  and records unavailable evidence explicitly.
- Qualification snapshots and ProjectRoleGrants are owned by the authorization
  module; ActorProfile/IdentityLink remain actor-owned, and ProjectRepository
  remains the canonical project loader. No duplicate grant/project repository
  is introduced.
- Only a Project Manager whose active grant covers the project can issue or
  revoke a contributor grant.
- The same covered `project.role_grant.manage` permission provides a scoped,
  paginated contributor-candidate lookup for the grant workflow. It returns
  only minimal actor fields, filters unauthorized rows before totals/cursors,
  cannot enumerate unrelated project activity, and never exposes issuer
  subject, identity-link metadata, contact data, skills, or reputation as
  authority.
- Target must be an active human and cannot be the issuing manager.
- A manager who separately holds a contributor grant cannot revoke that grant
  through their own administrative request; denial is stable and audited.
- A partial unique index on `(actor_profile_id, project_id, role) WHERE status =
  'active'` permits at most one active grant for the same exact role while a
  contributor may hold active submitter, reviewer, and adjudicator rows
  concurrently.
- Issue never revokes another role. Regrant after revocation creates a new
  immutable row.
- Typed schemas, audit facts, idempotency evidence, and current PostgreSQL
  validators accept only `submitter`, `reviewer`, and `adjudicator`; only issued
  and revoked success events remain. `both`, replacement fields/events/reasons,
  aliases, and conversion branches are absent.
- Snapshot ownership is composite across snapshot ID, actor, project, and exact
  requested role. There is no replacement/supersession column.
- Create and revoke require canonical request hashing: same key and
  same request returns the committed graph; same key with different request is
  rejected.
- Issue hashing includes the exact requested role. Same key/different role is
  `idempotency_mismatch`; a new-key duplicate same-role issue is a stable audited
  conflict; distinct keys may issue different roles concurrently. Revoke derives
  role from the locked grant and replay reloads/re-authorizes before disclosure.
- State, idempotency result, audit event, and invalidation event commit in one
  transaction.
- Only manual creation is enabled; automated schema value cannot be emitted.
- Revocation is visible on the next authorization context build.
- Revocation evidence and invalidation identify the exact revoked role;
  downstream consumers reconcile only the matching task, review, or future
  adjudication responsibility.
- The linked invalidation retains exact grant and cause-event references. A
  submitter revocation creates only the task-assignment obligation and reviewer
  revocation may create only its exact REV-owned review obligation. Adjudicator
  revocation persists exact invalidation only and creates or consumes no
  adjudication obligation until that separately approved lifecycle is active.
  No path changes another project role or an AdminRoleGrant.
- Project manager/admin role alone never creates contributor capability.
- PostgreSQL concurrency tests cover identical-role creates, concurrent
  different-role creates, regrant versus revoke, and revocation versus
  authorization.
- `POST/GET /api/v1/projects/{project_id}/role-grants`, grant detail, and grant
  revoke routes have multi-role, self-revoke, scope, privacy, rate-limit,
  replay, and negative tests.
- Every protected grant/candidate route declares one active `ActionId` mapped to
  `project.role_grant.read` or `project.role_grant.manage` against the
  canonically loaded project/grant target. Generated manifest-delta tests prove
  every surface introduced here has exactly one declaration.
- Contributor-candidate lookup has covered-manager allow, uncovered/cross-
  project deny, pagination/count concealment, minimal-field, rate-limit, and
  inactive/non-human exclusion tests; no UUID must be recovered from logs or
  direct database access.
- Migration `0026` enforces exact three-role checks, composite snapshot/grant
  ownership, partial unique/supporting indexes, database-time fields, and
  immutability. Migration `0026` refuses upgrade when obsolete combined or
  replacement evidence exists and never converts or deletes those rows. It
  replaces current audit/idempotency validators without editing historical
  migrations and refuses an unsafe downgrade without mutating evidence.
  Prior-head, fresh replay, preserved history, and both refusal paths are tested.

## Verification commands

```bash
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic upgrade head)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic downgrade -1)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic upgrade head)
(cd backend && .venv/bin/python -m ruff check app tests)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q \
  tests/test_authorization.py tests/test_auth.py tests/test_actors.py \
  tests/test_projects.py --cov=app.modules.authorization \
  --cov-report=term-missing --cov-fail-under=90)
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

Review exact-project scope, self-grant protection, role-specific snapshot
privacy, independent issue/revoke semantics, and absence of implicit grants.

## Stop conditions

Stop if contributor authority depends on a token role, inferred qualification,
project ID supplied without canonical database resolution, compatibility for
`both`, evidence conversion, or a mutation path that bypasses AUTH-PREP.
