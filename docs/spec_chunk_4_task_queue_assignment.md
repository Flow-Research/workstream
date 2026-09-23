# Task Records and Assignment

## Current boundary

Workstream is developing its first, unreleased v0.1. This specification covers
the existing task-record and assignment foundation, including the bounded
[project-grant authorization replacement](../.commitrail/changes/task-project-grant-authorization.md).
CP08 delivers exact contribution-policy lineage through task, assignment and
hidden Submission creation. It does not claim the complete public task queue,
submission public cutover, or authority-invalidation worker is delivered.
The [capability ledger](roadmap_status.md) distinguishes those remaining owners.

## Planned contributor lease and voluntary skip

The adopted [lease/skip plan](../.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-03CLP.md)
requires project-configured, claim-relative contributor leases and voluntary
skip before public task completion. This behavior is **not implemented yet**.
PostgreSQL time starts and expires each exact assignment. Skip or expiry returns
unsubmitted work to `ready`, retains the terminal assignment, and permits a new
claim by any authorized contributor, including the same person. A new claim
gets a new assignment ID; old preparation/admission cannot transfer to it.
Foreground preparation and Submission creation reject expired assignments even
when periodic Celery cleanup is delayed. Expose an own-assignment expiry reason
without disclosing another contributor. Existing task deadlines and reviewer
leases are separate; already-created Submissions are never reopened by this flow.

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
- The guide's ContributionPolicyVersion is locked before work becomes claimable
  and copied through assignment and hidden Submission creation by CP08.
  Claim does not perform a fresh CON lookup.

For claim/start, the actor/action/idempotency-key receipt is reserved first;
task and assignment are then locked, followed by canonical actor, identity
link and applicable grant revalidation and locking. This matches hidden
Submission creation's lock order. Authorization consumes the exact locked
facts before writes. Product writes and their audit evidence commit or roll
back together.

The receipt actor foreign key is checked at commit, after AUTH's actor lock;
reservation must not take an earlier implicit actor lock that can deadlock
parallel commands from the same actor. Referential integrity remains enforced.

## Claim and start retries

`POST /api/v1/tasks/{task_id}/claim`, `POST /api/v1/tasks/{task_id}/start`, and
`POST /api/v1/operations/tasks/{task_id}/start` require one UUID `Idempotency-Key`
header. Retrying the same actor/action/key and semantic request returns the
original typed success response only after fresh current authorization and
exact task, active assignment and locked-context checks. Claim replay requires
the task still be claimed; start replay requires it still be in progress.
No duplicate assignment or lifecycle success event is created. A fresh AUTH
decision records the replay's current authority check.

The key is not a permission. Revocation, suspension, a different assignment or
an incompatible current task state yields the normal concealed denial. Only
after authority succeeds may the caller receive `409 idempotency_mismatch`
for changed input or `409 task_replay_state_changed` for inconsistent stored
result/context. Keys are scoped by actor and operation, not by task: reusing a
claim key for another task is a mismatch, not a second claim. The receipt and
all business/audit writes commit or roll back together. Committed receipts
cannot be modified, deleted or truncated through ordinary SQL.

Revocation immediately prevents subsequent contributor commands. Closing an
existing assignment and returning a task to the ready queue through durable
invalidation has a hidden ARCH-03B9 operation. ARCH-03C1 supplies real service authority;
producer wiring and registration remain ARCH-03C2; a denied start is not proof
that an invalidation worker has run.

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

## Hidden ready queue facts

ARCH-03B2 provides `ReadyTaskQueuePort` through `TaskRepository`: an internal
data-owner read, not an HTTP route or authorization decision. It returns only
ready tasks in one exact project with no assigned contributor and no active
assignment. These predicates apply before `(created_at, id)` pagination and the
bounded `limit+1` query. Released assignment history does not hide eligible work.

The detached summary includes IDs, title, task type, difficulty, immutable skill
tags, estimated minutes and creation time. It excludes source metadata, actor
identity, policy bodies/hashes and artifact references. The project-bound cursor
is a position, not a permission token. The read performs no flush, commit or row
lock. Pages are live views, not reservations; claim rechecks authority and state.

ARCH-03C must authorize the exact project collection before calling this port
or using a client cursor, with current-grant/revocation and concealment proof.
No per-task AUTH handle or token role can substitute for that collection gate.
ARCH-03B8 supplies hidden task audit evidence. ARCH-03B9 supplies the hidden
assignment-invalidation operation; ARCH-03C1 supplies its real authority.
Producer wiring and public evidence access remain separate.


## Hidden management and operational queues

ARCH-03B3 extends the existing TaskRepository with `ManagementTaskQueuePort`
and `OperationalTaskQueuePort`. Each reads all task states within one exact
project, including draft, active work and post-submit states. These are internal
owner facts; ARCH-03C still owns separate manager/operator permissions and routes.

Management summaries contain task/project IDs, title, task type, difficulty,
immutable skill tags, estimated minutes, status, deadline and creation/update
timestamps. Operational summaries contain only task/project IDs, status and
creation/update timestamps. Neither includes descriptions, acceptance/rejection
text, source/import metadata, contributor identity, policy or artifact content.
There is no token-role switch or caller-selected projection.

All three queues use the single `TaskQueueRequest` and `TaskQueueCursor`
contract. Project/cursor filtering precedes bounded pagination; an extra row
alone supplies continuation. The ready queue retains its independent eligibility
filters. Cursors identify a live position, not authority, audience or membership.
No queue flushes, commits, rolls back or takes a row lock. No counts, reservation
or snapshot guarantee is supplied. Later authorized composition must validate
exact project authority before using an untrusted cursor.

## Hidden contributor and management task detail

ARCH-03B4 adds separate `ContributorTaskDetailPort` and
`ManagementTaskDetailPort` reads to TaskRepository. Each requires exact project
and task UUIDs. Contributor detail additionally requires a caller-bound
contributor UUID and returns unassigned READY work or exact own-active-assignment
work. Both task assignee and assignment contributor must match, with exact
assignment task/project membership. Released history cannot confer access; it
does not hide otherwise unassigned READY work. This is object visibility, not
a permission decision; future public callers must establish current exact
authority and must not trust a caller-supplied contributor identity.

Both immutable detail values contain title, description, type, difficulty, tags,
estimate, status, acceptance/rejection criteria, deadline and timestamps, with
task/project identity. Manager detail additionally contains source type/ref/hash,
import/external IDs and creator/assignee display facts. Contributor SELECTs never
load those private columns. Neither projection loads policy bodies, locked
hashes, artifacts or retired payment fields. SQL filters project/task/visibility
before returning a result; missing and invisible tasks both yield no result in
one query. Reads do not flush, commit, roll back or lock the caller's work.

These detail ports remain internal as standalone reads. ARCH-03B5 reuses them
in existing authorized work-context responses below. The existing standalone
detail endpoint and command response consumers still require their exact ARCH-03C
authority/cutover; no parallel public route or compatibility alias is added.
ARCH-03B8 supplies the bounded internal audit evidence read described below.


## Current contributor and manager work context

ARCH-03B5 replaces the response contracts of the existing authorized work-context
routes. Their actions, actor binding, project authority and task/assignment/AUTH
lock order stay the same. It does not activate other proposed ARCH-03C surfaces.

Both return `task`, `project`, `guide`, `review_policy`, `revision_policy`, and
`contribution_policy_version_id`. Task uses the fixed 03B4 audience-specific
facts (`task_id`, with no economic fields); guide owns `version`. The policy
references reuse PROJECTS `GuidePolicySelection`: `policy_id`, `generation`,
and `policy_hash`, taken from the validated historical activation receipt. The
ContributionPolicy version is that same receipt's exact UUID, already checked
against the task stamp. New guide activation does not replace an existing
attempt's policy references. No CON lookup or economic rules are exposed.

Only contributor context has `lifecycle`, with `assigned_to_current_actor` and
`next_actions`. Unassigned READY advertises `claim`; own CLAIMED advertises
`start`; other own-active states have no action hint. Task status appears only in
`task.status`. Hints never authorize execution. There is no `can_submit` flag or
precheck capability; hidden submission creation is not advertised as usable.
Manager task facts include source/creator/assignee display fields, without
contributor lifecycle or hints. The old shared work-context schemas and builders
are removed, not aliased.

The read reuses complete frozen-policy validation and the existing AUTH decision
inside its owner transaction. Successful reads persist their exact AUTH allow
record, without changing TASK lifecycle/assignment/receipt state. Missing detail
after authorization returns 404 `resource_not_found` and rolls that decision back;
missing or invalid locked custody returns the existing 422
`task_locked_context_invalid`. Ordinary unassigned draft is not contributor work;
a fully locked own-active draft remains visible under the existing authority rule.

Standalone detail endpoints, retained audit-route authority replacement, and
assignment invalidation retain their separately scoped work.

## Task locked-context projections

ARCH-03B6 replaces the shared operator-labelled response with strict immutable
`ManagementTaskLockedContext`, `OperationalTaskLockedContext` and
`AuditTaskLockedContext` composites in TASK schemas. All contain task/project
UUIDs and the exact historical guide version, source snapshot ID/hash, effective
submission-policy ID/hash, pre-submit policy ID/bundle hash, post-submit policy
ID/version/hash, review and revision ID/generation/hash and ContributionPolicy
version UUID. Management alone adds the bounded post-submit summary (schema
version, checker ID groups and blocking severities); its collections are immutable.
Operational/audit results exclude bodies, work/source content, actor identities,
artifacts, storage locations and economics.

The three hidden owner reads require exact project/task UUIDs, filter both before
resolving policy custody and lock TASK before PROJECTS. They use the existing
historical validator, including exact activation-receipt and stored-body checks;
a newer active guide does not change the result. They neither flush nor commit
caller-owned work and do not grant authority. Missing and foreign tasks conceal
identically; incomplete or inconsistent locks fail with `task_locked_context_invalid`.

The retained `/tasks/{task_id}/locked-context` route returns the same management
projection under its existing role/creator wrapper and loads the task once.
ARCH-03C still owns replacement of that authority and public operational/audit
activation. There is no audience-switching endpoint, fallback schema or new
TASK public API dependency. Retained audit-route authority replacement remains
separate ARCH-03C work.


## Task submission requirements projections

ARCH-03B7 replaces the shared mutable response with strict frozen
`ContributorTaskSubmissionRequirements` and `ManagementTaskSubmissionRequirements`
in TASK schemas. Both contain the same safe task/project IDs, guide version,
policy schema/merge identifiers, required packet/artifact/evidence fields,
forbidden artifact rules, attestations, hashing/storage rules, size limits and
packaging. Nested models are frozen and collections are tuples; JSON arrays
remain arrays. Packaging exposes only `package_required` and optional
`allowed_package_formats`, matching the effective-policy merge contract.
No source metadata, actors, economics, storage object locations or complete
policy bodies are exposed. A described format is not a claim of runtime support.

The management read reuses the existing historical context resolver. Contributor
requirements first acquire the same exact project/task row lock, then reuse the
existing detail visibility query, then resolve PROJECTS custody. A ready unassigned
task with no active assignment is visible, including released assignment history;
otherwise the task assignee and active assignment contributor must both match.
Missing, foreign and invisible tasks conceal identically before policy reads.
Invalid selectors reject before SQL. Both methods preserve caller transactions
without implicit flush, commit, rollback or nested transaction, and keep original
requirements after a successor guide activates. They grant no authority.

The existing `/tasks/{task_id}/submission-requirements` route uses the same
contributor-safe constructor for its current callers, including managers. Its
existing role/creator visibility wrapper remains an explicit ARCH-03C dependency;
it loads and locks TASK once before visibility and historical policy resolution.
The distinct manager model/read is internal and absent from OpenAPI. There is no
new public route, generic audience selector, compatibility alias or new compiler.

## Hidden task audit evidence

ARCH-03B8 supplies `AuditTaskEvidencePort` through `TaskRepository`, delegating
one fixed-column query to the shared audit owner. This is internal lifecycle
evidence for future covered Audit Authority access; ARCH-03C owns exact live
authority and routing. Existing contributor/manager audit reads and submission
recovery remain separate current consumers until their authority cutover.

The request binds exact project/task UUIDs and a 1..100 limit. Its cursor binds
that same scope and `(created_at, event_id)`. One TASK-left-join-AUDIT statement
filters canonical project membership, lifecycle domain, task identity and cursor
before limit+1. A missing or foreign task yields None; existing empty/exhausted
history yields an empty page. Equal timestamps use event UUID ordering. This is
one statement snapshot, not a durable export or current-at-return guarantee.

Items contain event ID/type, optional from/to status, stored actor attribution,
creation time, and optional assignment/authorization-decision IDs. Canonical
claim/start events require both references and exact nested project/task IDs;
malformed evidence fails with a sanitized error. SQL selects reference scalars
only for the typed audit writer and canonical claim/start event types; generic
rows cannot acquire canonical provenance by copying their tokens. Other events
gain no inferred references. SQL extracts only four named JSON scalar references and never loads
raw claims, roles, external identity, reasons, arbitrary payloads or policy bodies.
It does not export authority-decision history or claim forensic completeness.

Reads are nonlocking and do not flush, commit or roll back. The caller retains
its transaction; later claim/command authorization never relies on these facts.


## Hidden exact-assignment authority invalidation

ARCH-03B9 supplies `AssignmentInvalidationOperation` and the transaction-owning
`TransactionalAssignmentInvalidationHandler`. No production handler is
registered. ARCH-03C1 replaces the unavailable authorization adapter with the
canonical fixed-service AUTH/PREP implementation for the sole
`task.assignment.authority_reconcile` action. Atomic AUTH producer wiring and
first registration remain ARCH-03C2.

Each `TaskAssignmentAuthorityInvalidationRequested` event (protocol version 1)
addresses one original project/task/assignment/contributor and one immutable AUTH
invalidation event. AUDIT verifies the linked cause: Submitter grant revocation,
profile suspension/deactivation or identity-link revocation. Reviewer/admin
changes and reactivation are not assignment-release causes. Each cause must
carry its canonical AUTH permission. The locked assignment must predate the
invalidation's recorded mutation time. New claims and invalidations stamp their
existing timestamps using PostgreSQL's clock after AUTH locks, so a transaction
started earlier cannot make a replacement assignment appear eligible.

OUTBOX first independently verifies the complete committed invocation envelope.
The effect transaction locks TASK, its exact assignment, feature authority, then
OUTBOX event and attempt. The final owner fence checks a live lease and exact
invoked generation after lock waits, retaining custody locks through commit.
Validity is checked at fence acquisition; this does not freeze wall-clock time.
No external I/O occurs after the fence. The dispatcher releases its own locks
before calling the handler and never acquires TASK locks.

Only consistent active claimed/in-progress assignments without any Submission
can become `authority_revoked`, with a release timestamp. TASK becomes `ready`
and clears `assigned_to`; its policy locks and all prior work remain intact.
Submitted/evaluation/review/revision work is unchanged. The existing manager
release operation gains no additional transition or permission.

One deterministic `TaskAssignmentAuthorityRevoked` lifecycle event identifies
the invalidation and original assignment and binds its exact authorization
reference, bounded authority-facts snapshot and canonical resource digest.
Both AUDIT and PostgreSQL recompute that digest and bind the exact assignment
and invalidation references. AUDIT validates its immutable ALLOW
decision, exact action/permission, actor, task/project and digest. The database
additionally binds the immutable actor identity to the exact reconciler service.
It commits with the effect and serves as the replay receipt. Historical replay
does not recheck the service's current lifecycle status. An old
event cannot select a replacement assignment; restoration does not restore
closed work. The handler acknowledges only after its transaction commits.
Malformed targets/causes and denied authority reject; uncertain effects remain
shared OUTBOX `UNKNOWN`, without automatic reinvocation.

ARCH-03C2 must publish bounded actor-wide/project fan-out atomically with the AUTH
mutation. It must not backfill or dispatch retained invalidation rows: their
transaction-start timestamps do not establish mutation chronology. Capture exact assignment IDs through a nonlocking TASK projection
while authority locks serialize claim. Producers must not acquire TASK locks
after AUTH locks. First production registration must also enforce the required
prefork worker/routing topology. Hidden feature-authority tests now use real
fixed-service PREP and PostgreSQL; they do not prove production event publication
or live broker delivery.
