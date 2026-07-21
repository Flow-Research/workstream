# Chunk Contract: WS-AUTH-001-10 - Project Qualification And Contributor Role Grants

## Status

Active contract repair after signed start event
`github-actions:29815937933:start`. Runtime implementation remains blocked
until the exact repaired contract passes required L1 plan review. AUTH-PREP is
merged through PR #162 and is the hard runtime prerequisite.

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

## Trusted-main baseline and migration custody

- Reviewed baseline: protected `main` at
  `5a8a924d9b3b347d4cc74b4682865518539c837e`.
- Current Alembic head: `0030_artifact_verification_fencing`.
- AUTH-10 owns only the next forward migration,
  `0031_project_role_grants`. It does not reserve a later number and does not
  edit any historical migration.

## Exact action, target, guard, surface, and revalidation inventory

All five actions are human-only, owned by `WS-AUTH-001-10`, active in the same
commit that exposes their route, and use only the retained permissions shown
below. A service principal is rejected before grant lookup. Every route has
exactly one OpenAPI `x-workstream-action-id` declaration.

| ActionId | PermissionId | Canonical target and facts | Candidate authority | Required guards and revalidation | Exact surface |
|---|---|---|---|---|---|
| `project.contributor_candidate.list` | `project.role_grant.manage` | locked/read canonical `Project(id, status)`; page cursor is not authority | active `AdminRoleGrant(project_manager)` whose system scope or exact `scope_project_id` covers the loaded project | active human caller and link; re-resolve caller grant and exact project scope before querying; return only active human profiles with active links; exclude caller before page count/cursor construction | `GET /api/v1/projects/{project_id}/contributor-candidates` |
| `project_role_grant.list` | `project.role_grant.read` | canonical `Project`; filters are status and one exact role only | covered Project Manager or covered Audit Authority permission candidate | active human caller/link; canonical project scope; authorization precedes count, cursor, and row query; response contains grant/snapshot identifiers and role history but no identity-link or contact fields | `GET /api/v1/projects/{project_id}/role-grants` |
| `project_role_grant.read` | `project.role_grant.read` | loaded `ProjectRoleGrant` joined to its canonical project; path project must equal row project | covered Project Manager or covered Audit Authority permission candidate | active human caller/link; exact-project scope; mismatch/not-found remains concealed before disclosure; replay is not applicable to this read | `GET /api/v1/projects/{project_id}/role-grants/{grant_id}` |
| `project_role_grant.issue` | `project.role_grant.manage` | canonical project plus locked target `ActorProfile`/exact link, exact requested role, and newly staged composite-owned qualification snapshot | active covered `AdminRoleGrant(project_manager)` only | PREP locks caller profile/link/matched manager grant first; feature then locks project, target profile/link, and active exact-role selector; target is a different active human with active link; role is one of `submitter`, `reviewer`, `adjudicator`; no active same-role row; consume recomposes all final facts before snapshot/grant/evidence flush | `POST /api/v1/projects/{project_id}/role-grants` |
| `project_role_grant.revoke` | `project.role_grant.manage` | loaded and locked grant, its canonical project, actor, exact role, status, and snapshot reference | active covered `AdminRoleGrant(project_manager)` only | PREP locks caller authority first; feature then locks project and grant; path project must match; active grant only; caller may not revoke a grant whose contributor is caller; consume revalidates exact role/status/project and stages role-specific invalidation | `POST /api/v1/projects/{project_id}/role-grants/{grant_id}/revoke` |

`project_role_grant.issue` and `.revoke` extend PREP with an exact-project
scope and a locked `ProjectRoleGrant` candidate path. Preparation never locks a
feature row, and feature code never chooses or supplies its authorizing grant.
The route owns the root transaction and commits once. Reads continue through
`AuthorizationService.require()`.

## Exact qualification snapshot and grant contract

`ProjectRoleQualificationSnapshot` is authorization-owned and contains:

```text
id, project_id, actor_profile_id, requested_role,
skills_snapshot, reputation_snapshot,
prior_project_work_refs, external_expertise_refs,
captured_by_actor_profile_id, captured_by_admin_role_grant_id, captured_at
```

`skills_snapshot` and `reputation_snapshot` are closed privacy-bounded objects
with `availability = available | unavailable`; unavailable records a bounded
reason token and no inferred score. References are caller-supplied UUID/string
evidence identifiers only after validation, are never dereferenced as
authority, and exclude contact data, issuer subjects, raw claims, secrets, and
free-form personal profiles. The composite key
`(id, actor_profile_id, project_id, requested_role)` is the ownership target of
the grant foreign key.

`ProjectRoleGrant` contains one immutable issuance row with exact role,
`status = active | revoked`, `grant_method = manual`, the composite snapshot
reference, granting manager/profile and matched manager-grant provenance,
database timestamps, bounded issue reason, and terminal revocation provenance.
Only lifecycle fields may change once, from active version 1 to revoked version
2. No update changes project, actor, role, snapshot, or issuance provenance.

## Exact route and pagination disclosure contract

- Candidate items expose only `actor_profile_id` and nullable `display_name`.
  They never expose `contact_email`, issuer, subject, identity-link ID/status,
  last-seen timestamps, skills, reputation, or activity in another project.
- Candidate filtering for active human/profile/link and caller exclusion occurs
  in SQL before `total` and keyset cursor calculation.
- Grant list/detail responses expose durable grant provenance and the bounded
  snapshot captured for that grant, but never external identity metadata or
  contact fields.
- Cursors are opaque, signed/canonical query digests bound to project, status,
  role filter, page boundary, and limit. Cross-filter or cross-project reuse is
  rejected as `invalid_request` without counts.
- Candidate/list/detail routes use the existing read-rate control; issue and
  revoke use the existing administrative mutation rate control.

## Allowed files

```text
backend/app/modules/actors/**
backend/app/modules/authorization/**
backend/app/modules/projects/models.py
backend/app/modules/projects/repository.py
backend/app/api/router.py
backend/app/db/models.py
backend/app/modules/audit/**
backend/alembic/versions/<then-current-next>_*.py
backend/tests/test_actors.py
backend/tests/test_projects.py
backend/tests/test_authorization.py
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
adding project-role routes without one exact active ActionId declaration
using Audit Authority or any system role to issue or revoke contributor grants
committing inside PREP, the authorization kernel, or a repository
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
- Issuance stages exactly two success events in the same transaction:
  `ProjectRoleQualificationSnapshotCaptured` and `ProjectRoleGrantIssued`.
  Revocation stages `ProjectRoleGrantRevoked` and one linked
  `AuthorityInvalidationRequested`; there is no replacement event.
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
- The then-current migration enforces exact three-role checks, composite snapshot/grant
  ownership, partial unique/supporting indexes, database-time fields, and
  immutability. It refuses upgrade when obsolete combined or
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
