# Task Records and Assignment

## Current boundary

Workstream is developing its first, unreleased v0.1. This specification covers
the existing task-record and assignment foundation, including the bounded
[project-grant authorization replacement](../.commitrail/changes/task-project-grant-authorization.md).
CP08 delivers exact contribution-policy lineage through task, assignment and
hidden Submission creation. ARCH-03C2 delivers exact assignment-invalidation
publication and registered delivery. ARCH-03C4 delivers the three public task
queues with exact project authority. ARCH-03C5 delivers distinct Contributor and
Manager task detail and requirements. Public Submission cutover remains pending;
the [capability ledger](roadmap_status.md) identifies its owner.

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
| `GET /api/v1/projects/{project_id}/tasks/ready` | Active same-project Submitter; active project; ready unassigned tasks |
| `GET /api/v1/projects/{project_id}/tasks` | Covering project or system Project Manager; management projection |
| `GET /api/v1/operations/projects/{project_id}/tasks` | System Operator; status-only operational projection |
| `GET /api/v1/tasks/{task_id}` | Active same-project Submitter; ready unassigned task or exact own active assignment |
| `GET /api/v1/tasks/{task_id}/submission-requirements` | Same exact Submitter authority; original locked policy requirements |
| `GET /api/v1/projects/{project_id}/tasks/{task_id}` | Covered Project Manager; exact project/task; all task states |
| `GET /api/v1/projects/{project_id}/tasks/{task_id}/submission-requirements` | Covered Project Manager; exact project/task and original locked policy |
| `POST /api/v1/projects/{project_id}/tasks` | Covered Project Manager; existing project; guide not required for draft |
| `POST /api/v1/tasks/{task_id}/screen` | Covered Project Manager; draft; approved active guide and complete policy lineage |
| `POST /api/v1/tasks/{task_id}/release` | Covered Project Manager; screening; frozen policy validation and nonblank decision reason |
| `POST /api/v1/tasks/{task_id}/claim` | Active same-project Submitter; ready, unassigned task |
| `POST /api/v1/tasks/{task_id}/start` | Active same-project Submitter; exact own active assignment |
| `GET /api/v1/tasks/{task_id}/work-context` | Active same-project Submitter; ready unassigned task or exact own assignment |
| `GET /api/v1/projects/{project_id}/tasks/{task_id}/work-context` | Covered Project Manager; exact route project and task |
| `POST /api/v1/operations/tasks/{task_id}/start` | System Operator; another contributor's active assignment and nonblank reason |

Locked-context and audit reads retain their existing wrappers. Their broader
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
ARCH-03C2 supplies atomic producer wiring and registered delivery. A denied
start is not proof that the Celery assignment-reconciliation handler has run.

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

## Ready queue facts and public authority

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

ARCH-03C4 authorizes the exact project collection before calling this port
or using a client cursor, with current-grant/revocation and concealment proof.
No per-task AUTH handle or token role can substitute for that collection gate.
ARCH-03B8 supplies hidden task audit evidence. ARCH-03B9 supplies the hidden
assignment-invalidation operation; ARCH-03C1 supplies its real authority.
Producer wiring and public evidence access remain separate.


## Management and operational queues

ARCH-03B3 extends the existing TaskRepository with `ManagementTaskQueuePort`
and `OperationalTaskQueuePort`. Each reads all task states within one exact
project, including draft, active work and post-submit states. These are internal
owner facts; ARCH-03C4 supplies separate manager/operator permissions and public routes.

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
The owner reads do not flush, commit, roll back or take row locks. No counts,
reservation or snapshot guarantee is supplied. The public composition validates
live project authority before decoding a signed, audience-bound cursor, locks
the actor, matched grant and project in the canonical order, and commits its
authorization evidence atomically with response construction. Each page records
the exact grant used; pagination never supplies authority.

## Contributor and management task detail

ARCH-03B4 adds separate `ContributorTaskDetailPort` and
`ManagementTaskDetailPort` reads to TaskRepository. Each requires exact project
and task UUIDs. Contributor detail additionally requires a caller-bound
contributor UUID and returns unassigned READY work or exact own-active-assignment
work. Both task assignee and assignment contributor must match, with exact
assignment task/project membership. Released history cannot confer access; it
does not hide otherwise unassigned READY work. This is object visibility, not
a permission decision. ARCH-03C5 establishes current exact authority before
calling these owner reads and binds contributor identity from the request actor.

Both immutable detail values contain title, description, type, difficulty, tags,
estimate, status, acceptance/rejection criteria, deadline and timestamps, with
task/project identity. Manager detail additionally contains source type/ref/hash,
import/external IDs and creator/assignee display facts. Contributor SELECTs never
load those private columns. Neither projection loads policy bodies, locked
hashes, artifacts or retired payment fields. SQL filters project/task/visibility
before returning a result; missing and invisible tasks both yield no result in
one query. Reads do not flush, commit, roll back or lock the caller's work.

ARCH-03B5 reuses these ports in authorized work-context responses below.
ARCH-03C5 also exposes their exact standalone Contributor and Manager reads,
replacing the old broad detail wrapper. Command responses retain their existing
contracts; no compatibility alias is added.
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

Retained locked-context and audit-route authority replacement remain separately
scoped. ARCH-03C2 already delivers authority-loss assignment invalidation.

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

ARCH-03C5 exposes `/tasks/{task_id}/submission-requirements` only to exact
Submitter authority, and `/projects/{project_id}/tasks/{task_id}/submission-requirements`
to covering Manager authority. Both reuse the same safe historical requirement
values, after locking TASK/assignment and consuming AUTH. The old role/creator
wrapper is removed. There is no generic audience selector, compatibility alias
or new compiler.

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
`TransactionalAssignmentInvalidationHandler`. ARCH-03C1 supplies the canonical
fixed-service AUTH/PREP implementation for the sole
`task.assignment.authority_reconcile` action. ARCH-03C2 delivers atomic AUTH
producer wiring and registers this sole production handler under enforced
prefork delivery. ARCH-03C4 separately delivers the three public queues.
ARCH-03C5 supplies detail and requirements authority; locked-context and audit
read authority remain separately bounded.

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

ARCH-03C2 publishes complete actor-wide/project fan-out in pages of 100,
atomically with the AUTH mutation. It never backfills or dispatches retained
invalidation rows: their
transaction-start timestamps do not establish mutation chronology. Capture exact assignment IDs through a nonlocking TASK projection
while authority locks serialize claim. Producers must not acquire TASK locks
after AUTH locks. The registered handler uses dedicated `workstream.outbox`
routing with enforced non-eager prefork execution. Real PostgreSQL tests prove
originating publication, rollback and both claim/loss orderings; a real Redis
and prefork drill exercises production delivery. Public queues are delivered
separately by ARCH-03C4; timed contributor leases and voluntary skip remain deferred.

### Manager readiness commands

Create, screen and release require exactly one UUID `Idempotency-Key`. Header
validation precedes canonical actor resolution and product SQL; token verification
and rate controls still apply first. Authority comes from a covering Project
Manager grant, never token roles or task creation attribution.

Each command commits its task change, AUTH decision, shared lifecycle evidence and
immutable replay receipt in one transaction. Create binds the project and full
normalized payload; screen/release bind the task and reason. A retry rechecks live
authority. An unchanged request returns its original result only while task state
and locked context still match. Task advancement conflicts; activating a successor
guide alone does not change the task's frozen policy selection. Separate actors
and actions have separate replay namespaces. These receipts do not invent an
assignment for manager work.

`TaskCreated`, `TaskScreened` and `TaskReleased` retain exact task/project/decision
references without assignment. Creation retains source type; screen/release retain
complete locked policy references. The internal audit projection exposes its fixed
scalar fields, including the decision reference, without private payloads.

A new command for an invalid task state is denied by AUTH with 403. A currently
authorized replay whose task has advanced returns 409 instead of mutating it.


### Exact detail and requirements authority

ARCH-03C5 replaces the broad task-detail response with the existing detached
`ContributorTaskDetail` and `ManagementTaskDetail` contracts. The identifier is
`task_id`, with no `id` alias; Contributor fields exclude source and actor facts.
The separate Manager route retains management work instructions and source
attribution without treating a Manager as a Submitter. Manager draft detail is
available; requirements fail with `task_locked_context_invalid` if the task has
no complete locked policy context.

Each read locks TASK and its active assignment before live AUTH actor/link and
grant validation. Requirements then resolve historical PROJECTS policy custody.
Current checker installation is not historical authority. Exact DTO validation
and serialization occur before committing the authorization decision, which
records the exact matched grant and a digest binding the locked TASK facts.
Projection or response failure rolls back ALLOW evidence. A valid missing,
foreign or denied selector has the same concealed 404; malformed UUID syntax
returns 422. Nonhuman callers are rejected before TASK access. These reads do
not authorize claim or submission, and no old role/creator wrapper remains for
them. Shared helpers used by retained submission/locked-context/audit reads are
not yet removed.
