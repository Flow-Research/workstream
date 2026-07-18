# Review And Revision Lifecycle

## Status And Authority

This document is the active normative implementation contract for the planned
Workstream v0.1 human review and revision lifecycle. The lifecycle described
here is not yet available in the production API. Each owning REV chunk must
merge hidden behavior, AUTH must activate the exact registered actions, and
`WS-REV-001-13C` must pass the joint release gate before any surface is exposed.

The implementation sequence is defined by
`WS-REV-001-review-revision-lifecycle/CHUNK_MAP.md` under `.agent-loop`. This
contract defines product behavior and subsystem boundaries; it does not itself
implement a route, database table, job, authorization evaluator, artifact
capability, contribution participant, or frontend.

## Precedence And Archival Inputs

The supplied WS-REV and WS-IMP Markdown/PDF files under
`docs/reference_specs/` are immutable archival inputs. They are provenance,
not the reconciled runtime contract. Their hashes remain in
`docs/reference_specs/SHA256SUMS`.

The revised WS-REV Markdown contains section 4.6's closed action/permission
table. Its supplied PDF companion does not. They are separately supplied
archival artifacts, not generated twins, and neither is edited to manufacture
agreement. This active contract reconciles that difference together with the
accepted repository ADRs, merged `WS-XINT-001` handoffs, and trusted-main AUTH,
ART, and CON planning contracts.

When sources disagree, precedence is:

1. accepted repository ADRs and architecture lockdown;
2. this active review lifecycle contract;
3. merged cross-initiative handoffs;
4. approved WS-REV chunk contracts;
5. archival reference specifications as historical design input.

The canonical API namespace is `/api/v1`. Archival examples with the old
root-level version namespace do not create an alias.

## v0.1 Boundary

The shipping path is:

```text
Project Guide -> Task -> Submission -> Checker admission -> Human Review
-> Revision or FinalAcceptance -> ContributionRecord
-> conditional CompensationAward -> asynchronous external fulfillment
```

Human review decisions are exactly:

- `accept`
- `needs_revision`
- `reject`

Adjudication is outside this initiative. The independent `adjudicator` project
grant remains recognized, but no adjudication action, queue, lease, policy,
state, decision, contribution type, readiness gate, or API is available in
v0.1. A future separately approved initiative may consume the immutable facts
defined here without changing their historical meaning.

Frontend implementation is also outside this initiative. WS-REV first proves
the backend contract, lifecycle guards, operational recovery, and live API
behavior.

## Canonical Identity And Authority

Every persisted human lifecycle identity is the canonical active
`ActorProfile.id`. This includes the Submission contributor, TaskAssignment
contributor, preferred reviewer, ReviewLease reviewer, Review reviewer, finding
author, accepted submitter, recording reviewer, and human administrative actor.
External issuer/subject values, email, token roles, typed legacy profile IDs,
display labels, and UUID shape never substitute for actor identity or authority.

Human review requires one exact active project `reviewer` ProjectRoleGrant plus
all resource, assignment, lifecycle, no-self-review, and actor-state guards.
Separate `submitter`, `adjudicator`, and administrative grants do not substitute.
Revoking reviewer authority does not revoke or mutate another grant.

Read operations use the request-scoped
`AuthorizationService.require(ActionId, ResourceContext)`. REV owns canonical
resource loading and typed ResourceContext composition. REV does not import
AUTH repositories or models, read grants, reconstruct permission unions,
register actions, integrate evaluators, change `ActionOwner`, or change action
availability.

### Current Work And Claim Choreography

All of these endpoints remain planned and unavailable until the owning REV
chunks provide hidden behavior, AUTH registers and activates their dependencies,
and REV-13C releases the product surface.

`GET /api/v1/reviews/current` is a concealed read, not a claim:

```text
freshly verify the Flow token and resolve canonical ActorProfile.id
-> require(review.queue.read, exact project/resource/lifecycle context)
-> return the caller's active lease, one server-selected offer, or none
-> create no ReviewLease, packet manifest, queue mutation, or policy freeze
```

`POST /api/v1/reviews/claim` uses this exact AUTH-first order:

```text
freshly verify the Flow token
-> AUTH PREP review.claim with exact request bindings
-> lock claim idempotency
-> lock the review lifecycle fence
-> lock ReviewQueueEntry
-> lock Task, TaskAssignment, Submission, and CheckerRun facts
-> recompose canonical final facts
-> AUTH validates all prepared-handle bindings, consumes the handle once,
   evaluates exact current authority once, and stages bounded evidence
-> freeze the reviewer ContributionPolicyVersion and append ReviewLease plus
   ReviewPacketManifest
-> stage audit/outbox rows and commit once
```

Any denial or race before the append follows the prepared-protocol rollback path
and creates no lease, manifest, policy freeze, audit, or product outbox effect.

## Prepared Mutation Protocol

Every protected review/revision mutation uses the AUTH-owned prepared protocol:

```text
AUTH locks current authority and returns an opaque prepared handle
-> REV locks canonical feature rows
-> REV recomposes final typed facts
-> AUTH validates bindings and current authority, consumes once, evaluates once,
   and stages bounded decision evidence
-> REV, task, ART, CON, audit, and outbox participants flush
-> the request route or service command commits once
```

The non-Pydantic, nonserializable handle is bound to the exact `AsyncSession`,
ActionId, actor-reference kind and ID, idempotency key, and canonical request
digest. Caller construction, serialization, forgery, or a wrong binding stages
no decision evidence, performs no feature mutation, and preserves the legitimate
unconsumed handle for its later exact first use. A stale or consumed handle,
including a losing concurrent duplicate, remains invalid and stages no new
state. Exactly one concurrent exact consumer may win.

When an exactly bound handle reaches evaluation but current authority or policy
denies, the transaction owner rolls back the dirty caller transaction. AUTH
restages the unchanged bounded denial evidence in a clean transaction and the
route or service command commits that evidence once. No REV, task, ART, CON,
shared-audit, or shared-outbox effect survives. If restaging fails, nothing
commits.

## Canonical Records

The existing `Submission` is the versioned submission identity. Domain prose
may say “Submission version,” but no competing `SubmissionVersion` table is
created. Each finalized Submission stores immutable same-task predecessor
lineage, the exact TaskAssignment and canonical submitter that produced it, the
complete resolved guide/task-execution policy context, and the server-derived
verified `artifact_hash` supplied by the ART submission/checker cutover.
Caller `package_hash` is not trusted or silently renamed.

REV adds these lifecycle records in later hidden chunks:

- `ReviewQueueEntry`
- `ReviewLease`
- `ReviewPacketManifest`
- `Review`
- `ReviewFinding`
- `ReviewEvidenceArtifact`
- `RevisionContextPreparation`
- `SubmissionFindingResponse`
- `FindingResolution`
- `FinalAcceptance`
- review decision and administrative idempotency aggregates
- reconciliation findings and resolutions
- shared-outbox review projection inputs
- joint lifecycle release-control state

Every valid reviewer decision appends one immutable Review. Every submitted
ReviewFinding and every later FindingResolution is immutable. Later rounds
append a new Submission, Review, findings, responses, and resolutions; they do
not edit prior judgment or evidence. No delete or edit endpoint exists for
these immutable records.

Findings use lifecycle meaning `blocking` or `advisory`; they do not use the
retired generic review severities `high`, `medium`, or `low`. A
`needs_revision` decision requires at least one unresolved blocking finding.
A `reject` decision requires a bounded human reason; structured findings may
also be submitted but are not fabricated merely to satisfy a schema.

## Policy Locks

`ReviewPolicy` locks routing preference, lease duration, capacity,
no-self-review, finding/evidence, and decision rules. `RevisionPolicy` locks
revision limit and deadline inputs. Task execution context remains separate
from contribution terms.

The submitter `ContributionPolicyVersion` freezes on the exact TaskAssignment.
The reviewer version freezes independently on each ReviewLease. Project Guide
rebase changes neither freeze. A later lease may freeze the then-current
reviewer terms without rewriting an earlier lease.

## Checker Admission

Only a durable, final, current post-submit CheckerRun outcome of `allow_review`
may admit the exact immutable Submission to human review. Admission records the
exact CheckerRun ID and verified binding facts. A retry, supersession, or
different Submission cannot silently replace that anchor.

Checker routing is not human judgment. A final needs-revision CheckerRun moves
the Task to contributor-readable `needs_revision` in the existing checker
transaction while retaining the Task's locked context. It creates no Review,
ReviewFinding, RevisionContextPreparation, reviewer contribution, or synthetic
human actor, consumes no human revision round/deadline, and does not use D6
closure. Checker remediation follows that exact CheckerRun lineage and must pass
the normal submission/checker spine before human review.

Queue schema migration performs no blanket historical backfill. A later audited
reconciliation may admit only an unambiguous latest finalized Submission with a
current successful `allow_review`, compatible `review_pending` task state, and
verified required bindings. Ambiguous legacy rows remain unqueued for explicit
operator remediation.

## Server-Selected Current Work

The reviewer cannot browse or choose from the full backlog. The current-work
operation returns exactly one of:

- the reviewer's active lease;
- one server-selected next offer within the requested project; or
- none.

If a reviewer holds an active lease in project A and requests project B, the
project-B response is none. It reveals neither project-A lease facts nor an
unclaimable project-B offer. Complete project queue inspection is a distinct
administrative capability.

A revised Submission receives a time-bounded preference for the reviewer who
issued the prior `needs_revision` decision. Preference expiry, reviewer decline,
or authority invalidation opens the same queue entry to FIFO routing without
resetting its age. v0.1 permits at most one active ReviewLease per human
reviewer and one active lease per queue entry.

Claim, release, decline, expiry, and invalidation transitions use PostgreSQL
database time, exact row locks, partial uniqueness, and stable race outcomes.
User claims do not use `SKIP LOCKED`; deterministic background batches may.

## Review Packet And Artifact Boundary

LocalStorage is development-only. MinIO proves the S3-compatible protocol in
local/CI. AWS S3 is the v0.1 hosted provider behind the provider-neutral
`S3CompatibleArtifactStore`. Cloudflare R2 and Flow Node remain deferred.

REV consumes only narrow ART v2 typed product capabilities. It never imports
the raw byte-only `ArtifactStore`, a concrete provider, ART repositories,
`ArtifactScratchManager`, `PreparedArtifact`, `CommittedArtifactSource`, object
keys, provider URIs, scratch paths, receipts, or credentials.

`ReviewPacketManifest` is an immutable REV semantic projection naming the exact
queue entry, lease, versioned Submission, admitting CheckerRun/results, stamped
guide or revision context, response-evidence relations, and ART binding IDs. It
stores no bytes, content digest, provider location, signed URL, scratch path,
receipt, or authorization-matrix data.

An active ReviewLease authorizes artifact bytes only for the single Submission
packet named by its manifest. Prior, expired, consumed, sibling, later,
cross-task, and cross-project leases cannot read those bytes. Authorized chain
history may expose bounded binding ID, relation, media type,
verification/availability, and required/optional metadata, but never bytes,
content digest, provider locator, signed capability, receipt, replica detail,
service scope, or credential.

Chain metadata is available only to the exact submitter represented in the
chain, the current leased reviewer, a prior reviewer who authored a Review and
still holds the exact project reviewer grant, or an explicitly authorized
Project Manager/Operator. Prior participation grants metadata history only;
artifact bytes still require the current active lease for the exact packet.

## Review And Response Evidence

Reviewer finding evidence and submitter response evidence use an ART-owned
two-phase candidate/finalize capability:

```text
preflight authority
-> provider upload and verification outside lifecycle locks
-> AUTH prepares final human authority
-> REV locks exact lease/finding/response lineage
-> ART locks candidate/admission/binding state
-> REV recomposes final facts and AUTH evaluates once
-> ART binding and immutable ReviewEvidenceArtifact relation flush together
-> caller commits once
```

Authority loss, lease expiry, assignment loss, or preparation supersession may
leave only an ART-owned unbound candidate governed by ART retention. It creates
no canonical evidence relation or product effect. Decision and resubmission
revalidate evidence lineage again.

ART owns bytes, candidates, bindings, verification, retention, provider
execution, and recovery. REV owns packet membership, evidence-slot purpose, and
the immutable relation from a finalized ArtifactBinding to the exact Review,
finding, response, or resolution evidence slot. Human bearer tokens and provider
locators never cross into storage calls.

## Decision Transaction

No canonical Review may commit without the mandatory WS-CON flush-only
participant. No production or test no-op participant exists.

Every valid decision follows this order:

```text
freshly verify the Flow token
-> AUTH PREP review.decision with exact request bindings
-> lock review idempotency
-> lock the review lifecycle fence
-> lock ReviewLease, ReviewQueueEntry, task, the exact
   Submission.task_assignment_id row, Submission,
   predecessor Review, finding/resolution lineage, and stabilized binding facts
-> recompose canonical final facts
-> AUTH validates all prepared-handle bindings, consumes the handle once,
   evaluates exact current authority once, and stages bounded evidence
-> append immutable Review, submitted findings, and resolutions
-> consume ReviewLease
-> close ReviewQueueEntry
-> CON reviewer operation creates completed_review and evaluates the
   ReviewLease-frozen contribution rule
-> apply the exact decision branch
-> stage shared audit and outbox rows
-> request route or service command commits once
```

The decision transaction performs no ART capability call, provider I/O, or
contribution-evidence projection. It consumes the stabilized server-derived
Submission `artifact_hash` as lineage.

### Accept

```text
Review(accept)
-> append FinalAcceptance linked to the Review
-> Task.status = accepted
-> TaskAssignment.status = completed
-> CON submitter operation creates accepted_submission from FinalAcceptance
-> evaluate the TaskAssignment-frozen submitter contribution rule
-> stage audit/outbox
-> commit once
```

### Needs Revision

```text
Review(needs_revision)
-> reviewer completed_review already created
-> append Review-rooted initial RevisionContextPreparation
-> Task.status = needs_revision
-> TaskAssignment remains active
-> no FinalAcceptance
-> no submitter ContributionRecord
-> commit once
```

### Reject

```text
Review(reject)
-> reviewer completed_review already created
-> block the same-task TaskAssignment
-> Task.status = rejected with bounded human reason
-> no FinalAcceptance
-> no submitter ContributionRecord
-> commit once
```

Reject changes no other task, project grant, or contributor capability. Checker
outcomes, storage failures, revision limits, deadlines, withdrawals, and
administrative closure never synthesize a reject Review.

Any failure in REV, task, CON, shared audit, or shared outbox staging rolls back
the Review, findings, resolutions, lease/queue transitions, task/assignment
effects, FinalAcceptance, contributions, awards, audit, and outbox together.

## FinalAcceptance

`FinalAcceptance` is an internal immutable REV fact created only as the
lifecycle consequence of an already-authorized `Review(accept)` transaction.
It has no public/manual creation API and no separate authorization action.

Required lineage is:

```text
id
project_id
task_id
submission_id
source_review_id
accepted_submitter_id
accepted_at
recorded_by
policy_context_ref
```

`submission_id` is the existing versioned Submission identity.
`accepted_submitter_id` is the canonical human ActorProfile on the Submission
and TaskAssignment. `recorded_by` is the canonical human ActorProfile on the
Review and ReviewLease. `policy_context_ref` identifies the immutable
ReviewPolicy governing that Submission.

PostgreSQL enforces unique task, source Review, and Submission acceptance plus
same-chain project/task/submission/reviewer/submitter/policy integrity and
immutability. v0.1 has no reopen or replacement path.

## Contribution And Compensation Boundary

`docs/spec_contribution_compensation.md` and ADR 0016 are the canonical CON
contract authority. This section defines REV's orchestration obligations at that
boundary. Merged CON-01 publishes contracts only; it implements no policy
persistence, contribution record, award, participant, or fulfillment runtime.

Every committed Review creates exactly one reviewer `completed_review`
ContributionRecord sourced directly from the Review and ReviewLease. Only
FinalAcceptance creates a submitter `accepted_submission` ContributionRecord.
CON never infers submitter acceptance from `Review.decision`.

The CON participant exposes two operation-specific flush-only inputs:

- reviewer input for every decision, containing Review, ReviewLease, reviewer,
  lease-frozen ContributionPolicyVersion, Submission/project/task lineage,
  AuthorizationDecision, request/correlation references, and stabilized
  `artifact_hash`; it contains no FinalAcceptance or submitter-policy facts;
- submitter input only after accept creates FinalAcceptance and applies accepted
  task effects, containing FinalAcceptance, TaskAssignment, submitter,
  assignment-frozen ContributionPolicyVersion, and the same locked lineage.

Database constraints keep the source shapes mutually exclusive and enforce one
`completed_review` per Review and one `accepted_submission` per
FinalAcceptance. Explicitly unpaid rules create no CompensationAward. Payable
money or project-points rules create immutable awards in the canonical
transaction as defined by CON.

External points/payment delivery occurs after commit through the shared outbox
and adapter boundary. Delivery failure cannot roll back or change Review,
FinalAcceptance, ContributionRecord, CompensationAward, or task acceptance.
Reputation policy and reputation-event implementation are deferred; the review
transaction does not write a reputation side effect.

## Controlled Revision Context

ADR 0010 is additive to immutable revised submissions. The task pipeline owns
the single Project Guide context used for both task execution and human review.
TaskAssignment stores only `task_id`; it does not duplicate a guide/context
lock. Each Submission stamps the exact guide ID, version, immutable per-project
activation sequence, source snapshot, and task-execution policy IDs, versions,
and hashes used for that attempt.

Controlled revision preparation applies only after an immutable human
`Review(needs_revision)`. Checker-caused remediation remains the distinct
CheckerRun-rooted path above and performs no guide rebase or human finding replay.

Revision preparation compares the prior Submission's stamped guide identity and
activation sequence with the project's currently active Project Guide pair:

- exact identity and activation-sequence match: `kept`;
- any different internally consistent active pair: `rebased`, recording
  `forward` or `backward`, including intentional reactivation of an older guide;
- missing, incomplete, revoked, internally inconsistent, or unsafe active
  context: `blocked` for covered Project Manager repair.

Version strings are never ordered. Activation sequence records chronology but
does not overrule which guide is currently active.

`RevisionContextPreparation` is immutable and rooted in the exact
`needs_revision` Review and prior Submission. It freezes the complete selected
next-attempt guide/source/task-execution policy context, context digest, outcome,
direction, change summary, source TaskAssignment, currently authorized target
TaskAssignment, preparation sequence, preparing actor/process, and audit link.
It does not contain or rebase a ContributionPolicyVersion.

Each episode forms one non-branching preparation chain: one root per Review,
one child per preparation, same task/Review/source lineage across an edge, and
sequence increasing by exactly one. The head is the row with no successor.
Task Context selects that head and then validates it; it never falls back to an
older preparation when the head is blocked, corrupt, revoked, or stale.

Task Context returns the frozen preparation, not a moving active-guide pointer.
A later guide activation cannot silently change a context already returned to
the submitter. Submission N+1 acknowledges the head ID and digest and stamps
that context exactly. If it is no longer valid, submission fails with an
explicit re-preparation requirement.

No guide rebase occurs during review. The reviewer evaluates the exact guide and
task-execution context stamped on the single Submission covered by
the active lease. History shows the prior and new guide versions, direction,
and change summary.

## Finding Replay And Resubmission

For a human-review origin, every unresolved blocking ReviewFinding requires one
immutable `SubmissionFindingResponse` from the assigned submitter, with response
text and optional finalized
evidence binding. Responses to advisory findings are optional unless the locked
policy explicitly requires them. The checker-remediation path instead exposes
only bounded contributor-safe CheckerResult messages/suggested fixes, requires
no fabricated ReviewFinding/response/resolution, and returns to open routing
after corrected checker admission.

A human-Review Submission N+1 links its immediate predecessor, exact preparation
head, required responses, evidence relations, and target TaskAssignment. A
checker-remediation Submission N+1 instead binds the exact final needs-revision
CheckerRun through its server-derived immutable
`remediation_source_checker_run_id` and retains the Task's existing locked
context; it has no preparation or ReviewFinding response. Both paths rerun the
existing finalization and checker spine. A new current `allow_review` creates a
queue entry preferred to the reviewer who issued the prior human revision
request. Corrected checker work enters ordinary open routing.

The later Review appends one immutable `FindingResolution` for each required
prior finding with the canonical result `resolved`, `unresolved`, or
`not_applicable` and bounded rationale/evidence. It does not change the finding
or submitter response.

Normal revision returns to the same assigned contributor. If that contributor
loses authority, the source Submission and TaskAssignment remain immutable. A
covered manager may assign a replacement against the durable human revision
episode and append one preparation successor whose target TaskAssignment is the
replacement. The old contributor cannot submit.

## Revision Limits, Repair, And Legacy Recovery

Exact human Review revision-round counting, deadline anchor, and boundary require
separate human approval before implementation. They are not inferred from
checker retries, task SLA, current time, or archival examples. Approved values
freeze on the Review-rooted episode and use database time.

Reaching a revision limit or deadline blocks new revision preparation and
`submission.create` with a stable policy error. It does not automatically reject
or close the task. The task remains `needs_revision` and its assignment remains
active until an authorized explicit command.

A covered Project Manager may use the planned, reason-bound, idempotent
`review.revision_obligation.close` command only after server-proven limit or
deadline exhaustion. It sets the task to canonical `cancelled`, releases the
assignment at database time, clears active-assignee projection, and closes any
queue entry as administratively cancelled. It creates no Review,
FinalAcceptance, ContributionRecord, award, fulfillment instruction, or
reputation effect.

Blocked/revoked/invalid context preparation is repaired only through the
planned `review.revision_context.repair` command. A covered Project Manager
acknowledges the exact current head ID/digest and reason; the command appends one
validated successor after project setup correction. It cannot edit history,
branch the chain, create an episode root, or bypass a frozen limit/deadline.

A historical checker-rooted task is proven by exact durable CheckerRun,
Submission, and matching audit lineage; it is not legacy solely because no
Review exists. A task that claims human Review revision but has no unambiguous
Review/root cannot use
normal repair. Reconciliation records the defect. An Operator may use the
planned evidence-linked `review.revision_context.legacy_close` command to set
the task `cancelled`, release the assignment, and close any queue with terminal
reason `legacy_revision_context_unrecoverable`. It creates no synthetic Review
or CON record.

## Action Inventory And Activation Custody

Merged AUTH-08 is historical provenance: 74 PermissionIds and 57 ActionIds,
with 9 active and 48 planned. Trusted main after merged AUTH-09D-A contains 74
PermissionIds and 65 ActionIds, with 15 active and 50 planned. AUTH-09A added
the common fixed-service schema and seven ART identities with eleven
memberships. AUTH-09B activates `actor.service.provision` for identities already
in AUTH's closed registry. AUTH-09C activates `actor.profile.read` and
`actor.identity_link.read`; AUTH-09D-A activates `actor.profile.suspend`,
`actor.profile.reactivate`, and `actor.profile.deactivate`. These merges do not
activate a review action or contain any of REV's six future service identities.

The review lifecycle currently depends on 24 unavailable actions:

- registered planned `submission.create`;
- 19 registered planned review actions; and
- four approved but unregistered REV actions defined below.

The proposed `artifact.review_evidence.binding.create ->
artifact.binding.create` service action is separate and is not one of the 24.
Future counts must be derived from trusted main at each AUTH gate; the four REV
actions and separate ART action are never collapsed into a promised total.

The exact delivery order is:

```text
AUTH planned registration and activation custody
-> required ART/CON capability plus REV hidden behavior and canonical facts
-> AUTH evaluator integration and exact action activation
-> REV-13C joint product-surface release
```

`WS-AUTH-001-REV-CUSTODY` transfers the 19 registered planned review rows to
seven exact AUTH activation groups without changing mappings, counts, or
availability. `WS-AUTH-001-PREP` supplies the prepared mutation protocol.
`WS-AUTH-001-REV-REG` registers the four additions below as planned.
`WS-AUTH-001-REV-05/06/07/08/09A/11/12` integrate and activate only their exact
merged hidden features. `WS-AUTH-001-REV-LIFECYCLE` activates the four additions
only after the REV-11A-D and REV-12A1-A4 hidden manifests are complete. REV-13C alone
exposes the already-active coherent product surface.

## Four-Action Registration Manifest

Registration adds no PermissionId, activates nothing, and claims no hidden
behavior already exists. All human actors below are canonical ActorProfile IDs;
all mutations use AUTH PREP, final-fact recomposition, route/service-command
transaction ownership, one commit, exact idempotency, and transaction-time
revalidation.

### `review.revision_context.repair`

- Permission: existing `project.task.manage`.
- Candidate: active covered Project Manager grant only.
- Planned surface: `POST /api/v1/tasks/{task_id}/revision-context/repair`.
- Resource facts: exact project, task, current/source assignments, prior
  Submission, originating `needs_revision` Review, episode, current head
  ID/digest, and current guide/policy facts.
- Guards: covered project, exact Review-rooted episode, exact current blocked or
  invalid head, nonterminal task, no crossed lineage, append one validated
  successor only, no root/edit/branch.
- Transaction revalidation: authority, project, task, assignments, prior
  Submission, Review, episode, head, and current guide/policies under canonical
  locks.
- Hidden behavior dependency: `WS-REV-001-11B` and the task-owned revision
  participant.

### `review.revision_context.legacy_close`

- Permission: existing `operations.reconcile.run`.
- Candidate: Operator AdminRoleGrant only.
- Planned surface:
  `POST /api/v1/admin/review-reconciliation/{finding_id}/legacy-revision-close`.
- Resource facts: exact unresolved
  `legacy_revision_context_unrecoverable` finding, project, task, assignment,
  optional queue, absence of a recoverable human Review/root, and proof that the
  state is not exact CheckerRun remediation.
- Guards: exact unresolved current finding, legacy task still
  `needs_revision`, no healthy/recoverable Review root, exact replay only.
- Effects: task cancelled, assignment released, queue administratively closed;
  no synthetic Review, FinalAcceptance, or CON record.
- Hidden behavior dependency: `WS-REV-001-11D`.

### `review.revision_obligation.close`

- Permission: existing `project.task.manage`.
- Candidate: active covered Project Manager grant only; Operator authority does
  not substitute.
- Planned surface:
  `POST /api/v1/tasks/{task_id}/revision-obligation/close`.
- Resource facts: exact project, task, assignment, originating human
  `needs_revision` Review, current preparation head, approved frozen
  limit/deadline facts, and server proof of the selected reached cause.
- CheckerRun-rooted remediation is not an eligible resource for this command.
- Guards: exact current head/cause, task still `needs_revision`, and terminal
  reason exactly `revision_limit_reached` or `revision_deadline_expired`;
  missing, not-reached, stale, arbitrary, crossed, or cross-project input denies.
- Hidden behavior dependency: `WS-REV-001-11B`.

### `review.lifecycle.activation.manage`

- Permission: existing `operations.reconcile.run`.
- Candidate: Operator AdminRoleGrant only; no service actor or background replay.
- Planned surface: authenticated lifecycle-control status and adjacent-phase
  transition commands; REV-12A1-A4/13C lock the exact URI before exposure.
- Resource facts: operation, singleton ID, expected generation/current phase,
  target phase, reviewed manifest digest, server-derived drain observations,
  bounded batch/deadline, and reason.
- Guards: one canonical singleton, exact generation/phase/digest, legal adjacent
  transition, required drain/cutoff readiness, exact replay or changed-replay
  conflict. Lease force release keeps its own action.
- Transaction revalidation: prepared authority, shared/exclusive advisory fence,
  row locks, final observations, one caller commit.
- Hidden behavior dependency: `WS-REV-001-12A1` through `WS-REV-001-12A4`.

## Fixed Service Identity Manifests

Each identity is a distinct fixed service ActorProfile with its own exact static
ActionId membership. None exists through AUTH-09B. Each requires a separately
reviewed AUTH enum/database-constraint/static-matrix extension, controlled
provisioning through the merged AUTH-09B capability, AUTH-09E admission,
cross-service and human denial proof, and later exact action activation. An
extension or admission activates nothing by itself and no catch-all review
service exists.

| Fixed service identity | Exact ActionId | PermissionId | Hidden consumer | Activation gate |
|---|---|---|---|---|
| `workstream.review.preference_expiry` | `review.preference_expiry.run` | `operations.timer.run` | REV-06 | `WS-AUTH-001-REV-06` |
| `workstream.review.lease_expiry` | `review.lease_expiry.run` | `operations.timer.run` | REV-06 | `WS-AUTH-001-REV-06` |
| `workstream.review.authority_invalidation_reconciliation` | `review.reconcile.run` | `operations.reconcile.run` | REV-11 | `WS-AUTH-001-REV-11` |
| `workstream.review.reconciliation` | `review.reconcile.run` | `operations.reconcile.run` | REV-11 | `WS-AUTH-001-REV-11` |
| `workstream.review.artifact_reference_reconciliation` | `review.artifact_reference.reconcile` | `operations.reconcile.run` | REV-12 | `WS-AUTH-001-REV-12` |
| `workstream.review.projection` | `review.projection.rebuild` | `operations.projection.rebuild` | REV-12 | `WS-AUTH-001-REV-12` |

The two reconciliation identities intentionally have separate memberships for
the same ActionId. Execution mode and scope are server-derived, never selected
by the caller.

## Planned API Surface

All routes remain unavailable until REV-13C. The final coherent `/api/v1`
surface includes separate capabilities for:

- reviewer current work;
- claim, release, and decline preference;
- exact leased Review Context;
- authorized bounded chain history;
- finding and response evidence intake;
- review decision;
- Task Context revision preparation read;
- human-Review revision submission with responses and distinct checker-
  remediation resubmission;
- administrative queue inspection, routing correction, force release,
  reconciliation, revision repair/closure, and lifecycle control.

Request JSON never supplies authoritative project relationships, provider
paths, CIDs, URLs, service scopes, candidate roles, or permission unions.
Administrative commands require dedicated actions, exact resources, bounded
reasons, audit, and idempotency.

## Reconciliation, Projection, And Notifications

Preference/lease expiry, reviewer-authority invalidation, lifecycle
reconciliation, artifact-reference reconciliation, and projection rebuild are
idempotent fixed-service jobs. Correctness does not depend only on scheduled
delivery; commands reload current PostgreSQL state and lazy request-time
recovery reuses the same transition services where specified.

The Review transaction appends one canonical shared-outbox projection event in
the same commit. Shared outbox owns claim/retry/dead-letter delivery state. ART
receipts are the only immutable projection delivery receipts. REV creates no
parallel delivery-status table.

Projection and notifications execute after commit. Failure changes only shared
delivery state and never changes Review, FinalAcceptance, task, contribution,
award, or fulfillment truth. Read models are projections and never become
authority.

## Joint Release Control

REV-12A is a non-executable split record. REV-12A1 through REV-12A4 collectively
add one hidden PostgreSQL-canonical `JointLifecycleReleaseControl`. It uses
compare-and-set phase history,
PostgreSQL advisory-lock fences, mandatory typed fence ports, and bounded drain
observations across review mutations, task submissions, queue admission,
authority-loss replacement, CON fulfillment-obligation writers, dispatch, and
callbacks.

Activation and shutdown are generation-bound and crash resumable. Shutdown
fences new admission, drains admitted commands and leases, captures the
immutable fulfillment-obligation cutoff after prior writers drain, permits only
same-generation pre-cutoff completion work, then disables. Timeout leaves the
phase unchanged for forward retry. No background job replays human Operator
authority or advances a phase. Reactivation requires a newly reviewed manifest.

This controller is product release state, not AUTH action availability. The
12A1 through 12A4 implementation exposes no public route; AUTH activates the
exact management action only after all four hidden manifests merge, and REV-13C
exposes and drills it.

## Error, Concurrency, And Idempotency Rules

- Canonical resource mismatches and concealed resources use stable bounded
  errors without cross-project disclosure.
- Expected uniqueness/claim races map to stable conflict or exact idempotent
  replay responses.
- Decision idempotency binds actor, operation, lease, Submission, and canonical
  payload; it is separate from AUTH authority idempotency.
- Administrative idempotency is a separate resource/payload aggregate and does
  not widen decision idempotency.
- Database time governs lease, preference, revision deadline, and release time.
- Remote provider calls never occur while review decision locks are held.
- Only database-classified serialization/deadlock failures receive bounded
  transaction retries.
- Rows of one type lock in ascending primary-key order under the cross-domain
  lock order; audit and outbox append after state locks.

## Implementation And Release Gates

The lifecycle is delivered one explicitly approved PR-sized chunk at a time:

```text
01 active contract and immutable registration/service manifests
02-04 policy/task alignment and hidden persistence
05-07 admission, routing, leases, context, and artifact evidence
08-10 decision/revision kernels and atomic FinalAcceptance/CON composition
11-12 recovery, reconciliation, projection, and observability
12A1-12A4 hidden joint release control and cross-domain fences
13 AUTH-active coherent API exposure and live proof
```

Each runtime chunk starts only after its exact AUTH, ART, CON, audit, outbox, and
task-owner dependencies are merged on trusted main. Missing typed capabilities
become separately approved owner chunks; REV does not implement them
opportunistically or add compatibility fallbacks.

The final live proof covers first submit, checker admission, current-work
selection, claim/release/expiry, active-lease packet access, evidence intake,
`needs_revision`, kept/forward/backward/blocked preparation, response/resolution
replay, preferred return and takeover, accept with exactly one FinalAcceptance,
reject, reviewer revocation, manager repair and closure, legacy recovery,
provider outage/integrity failure, transaction rollback, contribution/award
source integrity, outbox retry, projection recovery, shutdown, crash resume, and
coherent reactivation.
