# Task Records and Assignment

## Current boundary

Workstream is developing its first, unreleased v0.1. This specification covers
the existing task-record and assignment foundation, including the bounded
[project-grant authorization replacement](../.commitrail/changes/task-project-grant-authorization.md).
It does not claim the complete task queue, contribution-policy lineage,
submission public cutover, or authority-invalidation worker is delivered.
The [capability ledger](roadmap_status.md) distinguishes those remaining owners.

## Records and ownership

- `ActorProfile` and `ActorIdentityLink` are canonical actor and external
  identity records. Identity admission is not permission to work.
- AUTH owns `ProjectRoleGrant`, actor/link lifecycle and permission decisions.
  Submitter and reviewer are project roles, not separate worker profiles.
- `WorkstreamTask` stores the project, source and work description, state,
  assigned contributor and locked guide/policy references.
- `TaskAssignment` records the actual contributor and enforces one active
  assignment per task.
- Shared audit evidence records authorized transitions. Claim/start evidence
  identifies the canonical actor, assignment and exact authorization decision;
  it does not copy token roles or claim snapshots as authority.

Removing an obsolete endpoint does not delete retained rows. Remaining
management/read and checker consumers must be traced before retiring shared
identity, policy or submission storage.

## Public task surfaces

Contributor commands and work context use canonical project authority:

| Surface | Authority |
|---|---|
| `POST /api/v1/tasks/{task_id}/claim` | Active same-project Submitter; ready, unassigned task |
| `POST /api/v1/tasks/{task_id}/start` | Active same-project Submitter; exact own active assignment |
| `GET /api/v1/tasks/{task_id}/work-context` | Active same-project Submitter; ready unassigned task or exact own assignment |
| `GET /api/v1/projects/{project_id}/tasks/{task_id}/work-context` | Covered Project Manager; exact route project and task |
| `POST /api/v1/operations/tasks/{task_id}/start` | System Operator; another contributor's active assignment and nonblank reason |

The older task-management foundation also retains create, detail, screen,
release, submission-requirements, locked-context and audit reads. Their broader
replacement and projection contracts remain owned by ARCH-03B/03C; this bounded
repair does not certify those routes as fully cut over.

There is no self-activation endpoint. A contributor cannot acquire permission
by creating a worker profile, supplying skill tags, or presenting a token role.
There is no public JSON-packet submission creation route. The existing
`GET /api/v1/tasks/{task_id}/submissions` remains a read, not evidence that POST
creation is usable. Admission-backed Submission creation stays hidden until
its separate canonical public integration is complete.

## Transitions and locked lineage

Stored task states use the canonical lowercase tokens:

```text
draft -> screening -> ready -> claimed -> in_progress
```

- Screening requires the existing project/guide and task-content prerequisites
  and stamps locked policy references; release requires complete locks.
- Claim validates the task's locked context and creates one active assignment.
- Normal start cannot borrow another contributor's assignment.
- Operator start does not reassign ownership or create a contributor grant.
- Existing locked context remains tied to the attempt. A later guide or
  policy publication alone is not permission to rewrite that context.
- The remaining readiness work must bind the guide's ContributionPolicyVersion
  before work becomes claimable and copy it through assignment and Submission.
  It must not add a fresh CON lookup during claim.

Task and assignment are locked first, followed by canonical actor, identity
link and applicable grant revalidation and locking. This matches hidden
Submission creation's lock order. Authorization consumes the exact locked
facts before writes. Product writes and their audit evidence commit or roll
back together.

Revocation immediately prevents subsequent contributor commands. Closing an
existing assignment and returning a task to the ready queue through durable
invalidation remains separately planned; a denied start is not proof that
such an invalidation worker has run.

## Work-context hints

Hints describe the current supported contributor command, not permission
tokens and not the full planned workflow:

- Ready and unassigned: `claim`.
- Claimed with the caller's exact active assignment: `start`.
- Otherwise: no contributor command hint.
- Management context does not advertise contributor commands.
- No `submit` or pre-submit execution hint is advertised by this surface while
  the canonical public submission integration remains hidden.

Pre-submission intake failures prevent Submission creation. Post-submission
evaluation concerns the submitted work and supplies evidence for
policy-governed routing; it does not own final acceptance.

## Required verification

- Real exact-project grants permit the supported commands without a worker
  token role; missing, revoked, reviewer-only and foreign-project grants deny.
- Suspended/deactivated actors and revoked or substituted identity links deny.
- Non-owner starts, inconsistent assignments and invalid locked context deny.
- System Operator authority is distinct from Project Manager and token roles.
- Concurrent claims have one winner; revocation and commands serialize.
- Audit/storage failure rolls back task, assignment and authorization evidence.
- Work-context hints match current authority, state and assignment.
- Removed endpoints, activation schemas and runtime bridge have no consumers.
- Required intake, immutable lineage and retained-data regressions survive
  fixture migration; no helper fabricates public submission success.
- Boundary checks, applicable tests, hosted coverage and focused reviews pass
  before the implementation is declared ready.
