# ARCH-03C5 — Exact-authorized task detail and submission requirements

- Initiative: WS-ARCH-001
- Durable disposition: Planned
- Intended merge outcome: contributor and manager task detail and submission
  requirements use exact live project authority and canonical detached projections.
- Risk class: L1 (authorization, public reads, immutable policy disclosure).

## Intent and current behavior

After merged ARCH-03C4, contributors can discover work through exact-authorized
queues. The existing task detail and requirements routes still call
`TaskService.get_task` and `get_task_submission_requirements`, using token roles
and creator/assignment checks. These are superseded authority paths.
ARCH-03B4/03B7 already supply the required detached owner projections.
`AuthorizedTaskCommands._locked_task`, `PreparedTaskAuthorization` and the AUTH
kernel already provide exact TASK/assignment-before-actor/grant lock ordering,
current authority, prepared consumption and decision evidence for work context.
Reuse this operation rather than creating another authorization subsystem.

## Bounded change

| GET route (under `/api/v1`) | Action | Permission / principal |
|---|---|---|
| `/tasks/{task_id}` | `task.read` | `task.queue.read`; exact-project Submitter |
| `/tasks/{task_id}/submission-requirements` | `task.submission_requirements.read` | `task.queue.read`; exact-project Submitter |
| `/projects/{project_id}/tasks/{task_id}` | `project.task.read` | `project.task.manage`; covered Project Manager |
| `/projects/{project_id}/tasks/{task_id}/submission-requirements` | `project.task.submission_requirements.read` | `project.task.manage`; covered Project Manager |

Contributor reads require ready/unassigned work or the exact own active
assignment, matching current work-context visibility. Managers read every task
state in the exact route project through project- or system-scoped Manager
grants. Creator attribution, token roles, Operator, Audit Authority, Finance,
Access Administrator, Reviewer and services grant no access. Missing, foreign
and unauthorized tasks conceal alike. A registered actor with revoked link or
suspended profile cannot retain access.

Detail uses the existing contributor/management detail projections; it does not
require locked policy context for manager draft tasks. Requirements validate the
existing locked historical context and installed plans through the canonical
owner methods. A newer guide must not replace the task's locked identity.
Manager access remains available through the separate project route; never
infer audience from token roles or treat Managers as Submitters.

### Allowed files and owners

- TASK `api/authorization.py`, `authorized_commands.py`, `router.py` or a focused
  TASK-owned read router, existing response schemas/detail contract docstrings;
  `service.py` only for deleting superseded wrappers and updating owner wording.
- AUTH `catalogue.py`, `domain/task_authority.py`, existing prepared task adapter
  and composition dependency; existing digest/action evidence registrations.
- Additive migration after `0002_task_queue_authority`, matching audit model
  constraint, Alembic head admission and schema/constraint fixtures.
- Affected callers and tests, new focused authorization task-read tests,
  canonical lane registrations and structural/ownership inventory updates only
  if actual changed targets require them; no limit relaxation.
- Current TASK/AUTH specifications, README, operating manual, roadmap, adopted
  ARCH sequence/overview and current initiative navigation; exports if present.

### Prohibited

No new grantable permission, generic read permission, token-role fallback,
compatibility route or response alias, lifecycle mutation, policy selection,
claim/start change, public Submission/checker/review activation, leases/skip,
frontend, external inference, retained-data deletion or baseline rewrite.
Locked-context and audit public authority remain the next distinct boundary.
Shared visibility/response helpers still used by retained Submission and audit
operations must remain until those consumers are replaced; identify them rather
than adding fallback behavior for the four replaced reads.

## Transaction and evidence

Extend the existing closed task operation/action set. Lock TASK then its active
assignment before AUTH actor/link and matched grant, preserving existing claim,
submission and role-mutation order. Consume exact prepared facts before owner
projection. Build and serialize the response before transaction commit. A failed
projection, historical-context validation, serialization or audit write must not
commit an allowed decision. Denials use existing rollback/restage custody and
concealment; do not change command denial behavior for unrelated operations.
Record the exact matched grant, actor, project/action and digest of locked task
facts. Add only the four exact action/permission pairs to database evidence.

## Acceptance and proof

1. Real signed HTTP role matrix covers both Contributor reads and both Manager
   reads, project/system Manager grants, foreign projects and forged token roles;
   assert exact recorded grant IDs and private-field exclusion.
2. Contributor visibility covers ready/unassigned, own claim/start, other active
   assignment, no active assignment, draft and revoked Submitter grant. Manager
   detail supports draft; requirements reject absent/corrupt locked context.
3. Absent/foreign/unauthorized selectors conceal consistently, including UUID
   syntax handling and nonhuman rejection before product access.
4. Real PostgreSQL proves live grant/link/profile revocation, lock order,
   refresh after waiting and rollback on projection/audit failure. Use distinct
   valid role/assignment fixtures rather than mocks of AUTH decisions.
5. Historical requirements retain original guide/policy identities after a newer
   guide is activated; never perform a current-policy substitution.
6. Migration preserves existing evidence, accepts each new exact pair, rejects
   wrong pairs and retains irreversible downgrade policy. Existing repository
   projection/requirements tests stay required; obsolete wrapper-only tests are
   removed or replaced without losing required behavior.
7. Public API drill follows queue discovery to contributor detail/requirements
   and claim/start, using real grants; manager calls use the new project routes.
   No old route/caller is restored to satisfy a test.

Verification: focused new signed-HTTP/PostgreSQL tests, affected TASK and AUTH
contracts, migration/schema parity, module/AUTH boundaries, structural inventory,
Ruff, Markdown links, Commitrail and full hosted Backend/real API checks. Use a
substituted grant/assignment or omitted guard probe that the targeted test must
detect. New behavior coverage remains at least 90 percent; preserve global floor.

## Review routing and reconciliation

Required: security and architecture/reuse plan review; QA/test-delta/product
operations plan review; focused implementation reviews for those risks plus
CI integrity and documentation. Human focus: exact audience/field separation,
contributor visibility, historic lineage and transaction/lock order.

Base: `47a6267f` after PR #437. No overlapping open product PR owns these reads.
The UUIDv7 fresh baseline and 0002 queue migration are canonical; no removed
migration graph is accepted. Leases/skip remain deferred. Next usable boundary
is the remaining locked-context/audit authority, then integrated task readiness
and the existing ART/post-submit execution sequence.
