# Decisions: WS-REV-001 Review And Revision Lifecycle

## Decisions

### D1 - Existing Submission Is SubmissionVersion

`backend/app/modules/tasks/models.py::Submission` is the canonical versioned
submission identity. WS-REV extends its relationships and constraints and may
use `SubmissionVersion` as domain language, but it does not create a competing
table or duplicate version chain.

### D2 - Production Artifact Provider Follows Repository Lockdown

LocalStorage is development/test only. MinIO proves the S3-compatible protocol
in local/CI. AWS S3 is the only v0.1 production provider. Flow Node and R2 remain
deferred. The revised WS-REV source and dependent reference material must be
corrected before canonical adoption.

**Human confirmed 2026-07-15.**

### D3 - Authorization And Storage Are Consumed, Not Reimplemented

Review code consumes the merged centralized authorization kernel and typed
artifact capabilities. Test fakes may model these ports. Production no-op
authorization, direct grant reads, raw provider paths, concrete provider
imports, compatibility aliases, fallback constructors, and dual factory paths
are prohibited.

AUTH owns construction of its request-scoped, session-bound dependency. The
request route or service command owns the caller `AsyncSession` transaction and
its only commit; AUTH, REV, task, ART, CON, audit, and outbox participants stage
or flush only. Merged AUTH-08 makes generic successful teardown roll back an open
feature-owned transaction, maps typed evidence persistence failures to the
stable retryable service-unavailable contract, and advances canonical actor
verification timestamps only in successful route-owned transactions. REV
retains these as regression invariants and does not patch AUTH implementation
locally.

Reads use request-scoped `AuthorizationService.require`. Mutations use AUTH's
prepared protocol: AUTH locks authority and creates an opaque, non-Pydantic,
single-use handle bound to the exact session, ActionId, actor-reference kind and
ID, idempotency key, and canonical request digest. REV locks canonical feature
rows and recomposes final facts, then calls AUTH. AUTH validates every binding and
current authority, consumes the handle exactly once, evaluates exactly once, and
stages decision evidence before the first feature mutation. Participants flush,
and the request route or service command commits once. Wrong-binding, forged,
serialized, or caller-constructed attempts against an unconsumed handle preserve
it for its later exact first use. Stale/already-consumed and concurrent duplicate
attempts remain invalid and stage no new state. Authority loss follows the
evaluated-denial path. REV never registers or activates actions.

REV receives ART v2 typed packet-read and evidence candidate/finalize ports, not
ArtifactStore, v1 verify/retain/release, ART repositories, provider references,
or scratch paths.

### D4 - Review Offer Is Server Selected

The reviewer current-work endpoint returns exactly one of active lease, next
offered review in a selected project, or none. It never returns full preferred
or open backlogs. If the reviewer holds a global active lease in project A and
requests current work for project B, the project-B response is `none`; it never
reveals project-A lease facts or an unclaimable project-B offer. Administrative
inspection is a separate permission and API.

**Human confirmed 2026-07-15.**

### D5 - Controlled Revision Rebase Remains Required

ADR 0010 remains active. A human `needs_revision` decision creates the need for
revision preparation, not an implicit mutation of the prior submission.
There is one Project Guide context shared by task execution and human review;
WS-REV does not create a separate reviewer guide or reviewer-side rebase.

The task pipeline owns context resolution. TaskAssignment stores only `task_id`
and does not duplicate or reference a guide/context lock. Every immutable Submission version
stamps the exact Project Guide and policy context used for that attempt. After
`needs_revision`, preparation compares the prior Submission's stamped guide
identity and activation sequence with the project's currently active Project
Guide:

- exact identity and activation-sequence match: keep the existing context;
- any different active identity or activation sequence: prepare the next attempt
  against that authoritative guide and record forward or backward direction;
- missing, incomplete, or unsafe active setup: block for Project Manager
  repair.

The Task Context API returns the prepared next-attempt context to the assigned
submitter before resubmission. Submission N+1 then stamps that context. The
prior task-attempt record and every prior Submission remain immutable. A
reviewer evaluates Submission N using the exact context stamped on Submission
N and performs no independent rebase. Both actors see the version transition
and change summary in history.

Preparation freezes the exact Project Guide/source snapshot and policy IDs,
versions, and hashes. Task Context reads that frozen preparation, not a moving
live guide pointer, and Submission N+1 must stamp it exactly. A later Project
Guide activation does not silently change an already returned revision context.
If the prepared context is revoked, corrupt, or otherwise invalid before
submission, creation fails with an explicit re-preparation requirement.

`RevisionContextPreparation` is an immutable task-owned record. Each revision
episode is rooted in the exact `needs_revision` Review for the prior Submission.
It contains that episode/Review identity, the complete next-attempt context,
context digest, outcome, change summary, prior Submission, target Submission
version, the reviewed Submission's immutable TaskAssignment, the currently
authorized target TaskAssignment, preparation sequence, preparing actor/process,
and audit link. Initial
`needs_revision` creates exactly one root before contributor access; manager
repair uses the dedicated authorized `review.revision_context.repair` command
to append a successor rather than editing it. Database constraints enforce
one root per episode, one child per preparation, same task/reviewed-assignment/
prior-Submission/episode across an edge, and a sequence increment of exactly one.
The target assignment normally remains the reviewed assignment. After AUTH-13
closes it for authority loss and a covered manager creates a replacement while
the Task remains in durable human-review `needs_revision`, the same caller
transaction appends one successor bound to that replacement assignment and
recomputes the current guide
classification. No edit or branch occurs, and the prior contributor loses
submission authority. Submission N+1 binds to that successor's target
TaskAssignment.
Thus the chain cannot branch and its only head is the row with no successor.
Task Context first selects that head and then validates it; blocked, revoked,
corrupt, or invalid head state never falls back to a predecessor. Initial work
comes from the task lock, revision work from the validated head, and submitted
history from each Submission lock. The revision submission acknowledges the
head ID/digest and commits Submission N+1 plus responses against it.

Existing Submission-to-WorkstreamTask equality FKs cannot represent a rebase.
They are replaced in chunk 09A with direct project/guide/policy/context
integrity constraints and a Submission-to-preparation binding. The original
WorkstreamTask locks and all earlier Submissions remain unchanged.

Guide ordering never compares version strings. Chunk 02A3 adds a per-project,
monotonic immutable `activation_sequence`. Existing active/superseded guides are
backfilled deterministically from effective time, creation time, and ID under
migration validation; drafts remain null until first activation. Active or
superseded state requires a non-null sequence, draft state requires null, and a
sequence is allocated exactly once while locking the project. Task stamps guide
identity in 02A4, Submission stamps it in 02C, and later preparation stamps it
in 09A. Equal identity/sequence keeps. Any different currently active guide
identity/sequence rebases, including an intentional backward rebase to an older activation
sequence. An internally inconsistent pair whose identity and activation sequence
do not belong to the same guide record, or incomplete/unsafe context, blocks for
manager repair.

**Human confirmed 2026-07-15:** one Project Guide; exact stamped guide identity/
activation-sequence match keeps; any different currently active identity or
sequence rebases forward or backward; Task Context returns the frozen
preparation; and the reviewer performs no guide rebase. The Project Guide active
during preparation is the authority frozen for the next task attempt.

Normal blocked/revoked/invalid preparation is recoverable only by a reason-bound,
idempotent covered Project Manager repair command that acknowledges the current
head and appends one validated successor after project setup correction. It
cannot create a root or rewrite a prior preparation. A legacy `needs_revision`
task is eligible only when neither an unambiguous human Review root nor an exact
final `needs_revision` CheckerRun exists. Valid CheckerRun-rooted remediation is
never legacy even when no human Review exists. The legacy state cannot be
repaired this way; an Operator
may close it through the separately authorized, evidence-linked legacy closure
with terminal reason `legacy_revision_context_unrecoverable`. That closure
releases the assignment and creates no Review or WS-CON record.

### D6 - No Synthetic Human Reject

Checker outcomes, revision limits, deadlines, artifact failures, withdrawals,
and administrative closure do not create a `Review(decision=reject)`. A reject
Review exists only when an authorized reviewer commits that decision under an
active lease.

**Human-approved behavior:** a reached limit/deadline blocks further revision
preparation and `submission.create` with a stable policy error but leaves the
task `needs_revision` and assignment active. It never closes automatically. A
covered Project Manager may use the dedicated, idempotent, reason-bound
`review.revision_obligation.close` command in chunk 11; that moves the task from
`needs_revision` to canonical `cancelled` with terminal reason
`revision_limit_reached` or `revision_deadline_expired`, atomically sets
`TaskAssignment.status=released`
and `released_at=database_now`, clears the task's active-assignee projection,
closes any queue entry as `admin_cancelled`, leaves the project grant unchanged,
prevents reclaim because the task is terminal, and creates no Review,
contribution, award, fulfillment instruction, or reputation
effect.

**Human confirmed 2026-07-15.**

The normal D6 command maps to existing `project.task.manage` and is not an
Operator reconciliation shortcut. Operator-only `review.queue.close` and
`review.revision_context.legacy_close` remain distinct recovery commands and
cannot close a healthy Review-rooted revision merely because a limit or
deadline exists.

### D7 - Artifact Preflight Does Not Hold Review Locks Across Remote Calls

Review evidence availability is preflighted outside the queue-row transaction.
The claim transaction then stabilizes and revalidates canonical binding facts
and the preflight identity before creating a lease. A subsequent provider
outage is handled as an outage during an active lease and cannot create an
adverse review outcome.

### D8 - No Canonical Review Commit Exists Without WS-CON

REV may land decision schemas, pure validation, and transaction input types
behind an unexposed boundary, but no service may commit a canonical Review until
the merged CON flush-only participant and ReviewLease/TaskAssignment
`ContributionPolicyVersion` freezes are mandatory. CON failure rolls back the
entire decision. No production or test-only no-op participant exists. AUTH may
activate `review.decision` only after the complete hidden REV+CON composition
merges.

### D9 - Canonical Review Projection Is Post-Commit

The Review transaction appends one canonical shared-outbox projection event in
the same PostgreSQL commit. Shared-outbox delivery state and immutable ART
receipts are the only delivery records; WS-REV creates no parallel request or
status table. A projection job stores the immutable projection after commit. Projection
failure changes only shared delivery state and never a Review.

### D10 - Frontend Follows Backend Proof

WS-REV-001 completes backend contracts, operational read models, and HTTP proof.
The React frontend begins only after these contracts and lifecycle guards are
stable, through a separately approved successor initiative.

### D11 - Coherent Public Release Is Atomic

Chunks 05-12A may implement and test internal services and routers, but the
production API composition exposes none of the reviewer/contributor lifecycle
mutations. After AUTH has separately activated every exact action, chunk 13
exposes current-work, claim, release, decline, context,
decision, revision preparation/resubmission, chain reads, and authorized admin
operations together only when AUTH, ART, WS-CON, audit, outbox, recovery,
reconciliation, projection jobs, and live preflight are mandatory and
proven. REV-13C changes product composition, not AUTH availability.

**Human confirmed 2026-07-15.**

### D12 - Shared Outbox And Lock Order Are Prerequisites

WS-REV uses the repository shared transactional outbox and the canonical
cross-domain lock order in `PLAN.md`. If either contract is unavailable at its
gate, the affected chunk stops for a separately reviewed foundation change;
review code does not create a private replacement or choose a local order.

### D13 - Historical Queue Admission Is Fail Closed

Queue schema migration does not create one entry for every historical
Submission. A later audited reconciliation admits only the latest finalized
version whose durable checker outcome is current `allow_review`, whose task is
compatibly `review_pending`, and whose required bindings are verified. Ambiguous
or legacy-incompatible rows remain unqueued for explicit operator remediation.

### D14 - Lease-Bounded Artifact Disclosure

Reviewer history and Review Context expose the authorized chain of Submission
versions, Reviews, findings, responses, resolutions, guide-version transitions,
and bounded audit facts. Artifact content is narrower: an active ReviewLease
authorizes only the immutable `ReviewPacketManifest` anchored to its single
Submission version. That packet contains the Submission bindings, the durable
checker-run bindings from the exact immutable CheckerRun ID stored on its queue
admission, its finding-response evidence bindings,
and required locked-context/source-snapshot bindings. Membership is derived
from canonical relations, never caller-supplied IDs. It does not authorize
artifact bytes from a prior, later, sibling, cross-task, or cross-project
submission packet. An expired or consumed historical lease is not current read
authority.

The manifest is a REV-owned semantic record containing only the exact queue/
lease, versioned Submission, admitting CheckerRun/results, locked guide/revision
context, response-evidence relations, and ART binding IDs. It contains no bytes,
digest, provider data, receipt, scratch path, or AUTH matrix facts.

Historical artifact projection is deliberately bounded to ArtifactBinding ID,
relation kind/purpose, media type, verification/availability state, and required
or optional classification. It excludes content bytes/excerpts, content digest,
provider URI/path/key/CID, signed capability, replica/receipt detail, service
scope, and credentials.

Chain metadata authorization is relationship-specific. It permits the exact
submitter whose immutable TaskAssignment/Submission appears in the chain, an
active reviewer leased to that chain, a prior reviewer who authored a Review in
that chain and still has the exact current project `reviewer` grant, or an explicitly authorized
Project Manager/Operator. It does not permit an arbitrary same-project reviewer.
Prior participation grants metadata history only; artifact content still
requires the current active lease for the exact Submission packet.

Reviewer finding evidence enters through typed ART intake under the active
lease and creates an immutable REV-owned `ReviewEvidenceArtifact` relation to
one ArtifactBinding ID. Its pre-decision slot is lease/operation scoped and is
later linked to the exact finding without changing binding identity. Submitter response
evidence uses the same ART boundary under the assigned submitter's
`submission.create` scope. Human bearer tokens and raw provider locations never
cross into storage calls.

Evidence upload uses an ART-owned two-phase candidate/finalize capability.
Provider I/O completes before finalization. AUTH then locks human authority,
REV locks lineage, ART's database-local participant locks candidate/admission/
binding state, REV recomposes final facts, AUTH evaluates once, and binding plus
`ReviewEvidenceArtifact` flush together.
Expiry, revocation, assignment loss, or preparation supersession during upload
may leave only an ART-owned unbound candidate governed by ART retention; it
creates no canonical binding/relation or lifecycle effect. Decision and
resubmission revalidate the relation again.

### D15 - FinalAcceptance Is The Sole Submitter-Acceptance Source

There is one immutable Review for each reviewed Submission version, with the
Review predecessor chain following the Submission predecessor chain. A separate
mutable "review version" entity is unnecessary. Both submitter and authorized
reviewer history views traverse all Submission/Review versions and bounded logs.

Every valid reviewer decision appends one immutable Review. Every submitted
finding and every later resolution is immutable; later revision rounds append a
new Review, findings, and resolutions rather than updating prior judgment.
Every committed Review creates exactly one reviewer ContributionRecord. When
that Review's decision is `accept`, REV also creates one immutable
`FinalAcceptance`; CON creates the submitter ContributionRecord only from that
fact. `needs_revision` and `reject` create no FinalAcceptance and no submitter
contribution.

The repository's existing immutable `Submission` row is the version identity,
so the handoff's conceptual `submission_version_id` is persisted as canonical
`submission_id`. `FinalAcceptance` contains `id`, `project_id`, `task_id`,
`submission_id`, `source_review_id`, `accepted_submitter_id`, `accepted_at`,
`recorded_by`, and `policy_context_ref`. `accepted_submitter_id` is the canonical
human `ActorProfile.id` on the reviewed Submission and exact TaskAssignment;
`recorded_by` is the canonical human `ActorProfile.id` on the source Review and
ReviewLease. The policy reference is a foreign key
to the exact immutable `ReviewPolicy.id` whose project/guide version matches the
reviewed Submission context. PostgreSQL enforces unique task, source Review, and
Submission acceptance, same-chain project/task/submission/reviewer/submitter
integrity, immutability, and human actor kinds.

FinalAcceptance has no public/manual create API and no independent authorization
action. It is created only as the internal consequence of an already-authorized
`Review(accept)` transaction. This v0.1 model has no reopen or replacement path;
future adjudication may consume immutable facts through a separately approved
lifecycle without changing this decision path now.

The CON participant exposes two operation-specific inputs derived exclusively
from locked immutable lineage. The reviewer input is required for every valid
decision. It contains Review, ReviewLease, the reviewer, the lease-frozen
reviewer `ContributionPolicyVersion`, the versioned Submission, project and task
lineage, the originating AuthorizationDecision, request and correlation
references, and the server-derived stabilized Submission `artifact_hash`. It
never contains FinalAcceptance or submitter-specific source or policy facts.

The submitter input exists only after the `accept` branch creates
FinalAcceptance and applies the accepted Task and TaskAssignment effects. It
contains FinalAcceptance, TaskAssignment, the submitter, the assignment-frozen
submitter `ContributionPolicyVersion`, and the same locked Submission, project,
task, authorization, request, correlation, and artifact-hash lineage. There is
no combined input with nullable FinalAcceptance and no submitter input for
`needs_revision` or `reject`.

CON copies the stabilized Submission `artifact_hash` to
`ContributionRecord.artifact_hash` and does not load, verify, or rederive it
through ART. The current caller-supplied `Submission.package_hash` is not that
field; the ART submission/checker cutover must add and bind the exact verified
value before REV-10.

CON creates one reviewer `completed_review` directly from Review and ReviewLease
and one submitter `accepted_submission` only from FinalAcceptance and
TaskAssignment.

Database checks keep those source shapes mutually exclusive, with one
`completed_review` per Review and one `accepted_submission` per
FinalAcceptance. A reviewer record requires `source_review_id` and
`source_review_lease_id` and requires both `source_final_acceptance_id` and
`source_task_assignment_id` to be null. A submitter record requires
`source_final_acceptance_id` and `source_task_assignment_id` and requires both
`source_review_id` and `source_review_lease_id` to be null. CON evaluates the
matching frozen ContributionRule, creates no award for explicit unpaid, and
creates immutable money and/or project-points awards when payable. Derived
inserts do not invent `contribution.materialize` or
`compensation.award.materialize` actions.

REV owns lifecycle orchestration inside the request transaction. It appends
Review, findings, and resolutions,
consumes the lease, and closes the queue entry. It then calls the mandatory CON
participant's flush-only reviewer operation, which creates `completed_review`
and evaluates the lease-frozen reviewer policy. REV next applies the decision
branch. For `accept`, it appends FinalAcceptance, applies the accepted Task and
TaskAssignment effects, and calls the participant's flush-only submitter
operation. That operation creates `accepted_submission` and evaluates the
assignment-frozen submitter policy. The other decisions do not call the
submitter operation. REV stages shared audit and outbox rows from every invoked
operation; the request route or service command commits once. A failure in CON
or any later REV stage rolls back
the entire decision. Core creation calls no ART capability and performs no
external I/O. External fulfillment and optional contribution-evidence
projection begin only after commit and cannot alter canonical acceptance or
contribution truth.

### D16 - Canonical Actor IDs Are Product Lineage

Every human identity persisted by review/revision is the canonical active
`ActorProfile.id`: Submission contributor, TaskAssignment contributor,
ReviewQueueEntry preference, ReviewLease reviewer, Review reviewer, finding
author, and human administrative actor. External issuer/subject, email, legacy
typed-profile row IDs, token roles, and profile labels are evidence or
compatibility data, never actor IDs or authority.

Protected preference expiry, lease expiry, review reconciliation, artifact-
reference reconciliation, and projection rebuild use distinct exact fixed
service ActorProfiles/static ActionId rows admitted through AUTH-09E. They never
enter human grant evaluation, borrow Operator authority, or occupy a human FK.
Shared outbox dispatch retains its separately owned identity. Authorization and
audit retain actor kind so UUID shape never implies human authority.

### D17 - Contribution Policy Freeze Is Independent Of Revision Context

Legacy compensation-context state is removed by WS-CON. It is not retained in the
final Project Guide, Submission, CheckerRun, Task Context, or
RevisionContextPreparation contract, and it is not replaced by the current
moving `ContributionPolicyVersion`.

Submitter `ContributionPolicyVersion` freezes once on the exact TaskAssignment;
reviewer `ContributionPolicyVersion` freezes separately on each ReviewLease. Forward or backward guide
rebase changes neither an existing assignment freeze nor an existing lease
freeze. A later lease may independently freeze the then-current reviewer terms.

### D18 - Authority-Loss Replacement Preserves Source And Changes Target

Normal `needs_revision` returns to the same contributor. The AUTH-13/14 final
contract nevertheless preserves a durable unassigned human revision episode when
that contributor loses authority and permits a covered manager to assign a
replacement. WS-REV adopts that dependency rather than stranding the task.

The episode permanently retains the reviewed Submission and its original
TaskAssignment as source lineage. Replacement assignment appends one immutable
preparation successor whose target assignment is the replacement and whose
guide context is freshly classified against the currently active Project Guide.
Submission N+1 binds to that target assignment, and WS-CON submitter attribution
and contribution-policy freeze derive from it. The old contributor cannot submit; no prior
Submission, assignment, Review, finding, or preparation is rewritten.

### D19 - Joint Release Control Is A Hidden Persisted Foundation

Safe product release/shutdown is product infrastructure, not proof-script state.
Chunks 12A1 through 12A4 own one PostgreSQL-canonical
`JointLifecycleReleaseControl`, the
hidden behavior and resource facts for the Operator-only
`review.lifecycle.activation.manage` action, advisory-lock-based
mutation fencing, typed internal fence ports, bounded drain observations, and
crash-resumable phase history. Every canonical phase change is a fresh
Operator-authorized adjacent transition; no background job replays the initiating human
or advances phase. It lands with no production lifecycle route and no action
availability change. `WS-AUTH-001-REV-LIFECYCLE` activates that exact action only
after 12A1 through 12A4 and all other additive hidden manifests merge.

Review, every task submission, review-queue admission, authority-loss
replacement, every CON fulfillment-obligation root creation, requeue, successor,
and repair writer, and compensation dispatch and callbacks consume the same
mandatory fence through explicit composition. CON retains fulfillment and
callback semantics and exposes mandatory obligation-writer, dispatch, callback,
drain-cutoff, and observation hooks; it does not create a second shutdown
controller. Every obligation-root writer acquires the shared fence before CON
allocates its server-derived monotonic ordinal. The exclusive
`admission_fenced -> commands_draining` transition waits for those writers and
atomically stores the CON-derived maximum ordinal as the immutable generation
cutoff. During `delivery_draining`, dispatch and callbacks may only complete a
same-generation root at or below that cutoff; root creation, requeue, successor,
and repair work remains denied. REV-13C exposes and exercises the merged,
AUTH-active foundation, performs the ordered writer fence, migration, and
process cutover, and prohibits downgrade after protected rows exist.

### D20 - Independent Roles And AUTH Activation Custody Supersede The Archive

The project roles are exactly independent `submitter`, `reviewer`, and
`adjudicator` grants. There is no combined role. Review behavior requires the
exact active reviewer grant and no-self-review guard. Reviewer invalidation may
change only review preference/lease/queue state; it never mutates submitter,
adjudicator, or administrative authority. Adjudication actions and lifecycle
remain unavailable and outside this initiative.

AUTH is the sole registration, evaluator, activation-custody, and availability
owner. `WS-AUTH-001-REV-CUSTODY` transfers the 19 registered review rows to seven
exact AUTH custodians without changing availability. REV feature chunks build
hidden behavior and feature-manifest deltas; the exact
`WS-AUTH-001-REV-05/06/07/08/09A/11/12` gates later activate their action groups.
`WS-AUTH-001-REV-REG` registers the four approved additions and
`WS-AUTH-001-REV-LIFECYCLE` activates them only after all hidden manifests merge.
REV-13C performs the separate product-surface release. The 24 REV dependencies
are one registered planned submission action, 19 registered planned review
actions, and four approved but unregistered additions; none is active. The
separate ART review-evidence binding proposal is not one of the 24, so future
counts remain current-main-derived rather than a promised fixed total.

### D21 - Parent REV-02 Is Split And AUTH Contributor Ownership Remains Prior

The user explicitly started parent REV-02, but required L1 plan review found the
combined guide, policy/lifecycle, and Submission migration unreviewable as one
chunk. Parent 02 is therefore a non-executable split record:

```text
02A parent split
  -> 02A1 Project/setup publication fence
  -> 02A3 guide activation chronology
  -> 02A4 Task guide triplet screening
-> 02B immutable review/revision policy and dormant task/assignment states
-> 02C Submission attribution/context/immediate-predecessor immutability
```

AUTH-09D-A merged through PR #148 as
`99ae4c963e53f317175dcb308b9e47c93ccf19ed`, establishing migration
`0026_actor_profile_lifecycle` and database-backed ActorProfile lifecycle
provenance. `WS-AUTH-001-CONTRIBUTOR-FOUNDATION` later merged through PR #153 at
`8d5eb15b` with migration `0027_contributor_foundation`. It clean-cuts both
retired task-subsystem contributor-identity fields to `contributor_id`, preserves
current behavior, and supplies database-backed canonical-human ActorProfile
lineage. REV consumes that exact merged contract and never supplies a parallel
rename, compatibility alias, or ActorProfile constraint. Each executable REV
child allocates a migration only from its then-current explicit-start head.

02B keeps terminal Task/Assignment values dormant. It adds no transition into
`accepted`, `rejected`, `completed`, or `blocked`, and no reject Review FK.
The Review decision/task participant owns those effects after immutable Review
persistence exists. The later reason-bound administrative command owns the
`cancelled` edge. D6 continues to prohibit synthetic reject.

The review preference and lease durations are independent positive policy
values. Neither may be inferred from `ReviewPolicy.sla_hours`; their exact v0.1
migration defaults remain a human decision before 02B can start.

### D22 - Checker Remediation Remains Distinct From Human Revision Rebase

D22 preserves the existing CheckerRun-rooted `needs_revision` path without
expanding ADR 0010. Checker remediation keeps the Task's locked guide context,
creates no Review/finding/reviewer contribution, consumes no human ReviewPolicy
revision round/deadline, and does not use finding replay or D6 close. Controlled
RevisionContextPreparation remains rooted in an exact
`Review(needs_revision)`. Corrected Submission N+1 persists the server-derived,
unique, immutable `remediation_source_checker_run_id` for the exact completed,
needs-revision, current-at-selection CheckerRun on its immediate predecessor.
Treating exact checker history as legacy or inferring it from a later current run
is prohibited.

### D23 - Human Revision Exhaustion Semantics Require Explicit Approval

D6 fixes the outcome of an exhausted human Review revision but does not define
the round counting source, deadline anchor, or inclusive/exclusive boundary.
Those values remain a human-owned decision before 09A1. They cannot be inferred
from checker retries, task SLA, current time, or archival examples. Whatever is
approved freezes on the Review-rooted episode, uses database time, and cannot be
bypassed through context repair.

### D24 - Guide Chronology Precedes Hidden Authorized Reactivation

Parent 02A is a planning-only split after L1 review rejected its combined
runtime boundary. 02A1 first makes the complete Project/setup writer graph share
one Project-first fence. 02A3 then adds activation sequence and canonical-human
approval provenance, freezes the complete activated guide row except exact
lifecycle transitions, and adds an explicit no-write active-repeat success while
preserving public superseded-candidate denial. 02A4 adds immutable Task guide
stamps and Project-first screening. After AUTH-PREP/custody and an
AUTH-12 contract amendment, 02A2 adds hidden
bodyless `If-Match` reactivation while `project.guide.activate` remains
unavailable. Its complete resource manifest gates AUTH-12 evaluator/cutover/
activation. This prevents new behavior from appearing under legacy local roles
or an already-active centralized action.

### D25 - Decision Lock Order Is Command Specific

The decision command computes its canonical request key/digest without a
database lock, then locks AUTH authority, ReviewDecisionRequest, the review
lifecycle fence, ReviewLease, ReviewQueueEntry, WorkstreamTask, exact
`Submission.task_assignment_id`, exact
Submission, and subordinate immutable lineage rows in stable ID order. This
preserves AUTH-first semantics and the user-confirmed ReviewLease-before-queue
order. Other commands publish their own orders; no vague universal lock order
substitutes.

### D26 - Lifecycle Phase Denies Execution, Not Static Registration

D26 narrows D19. Persisted lifecycle phase controls command execution through
mandatory database fences. It does not unregister FastAPI routers, deactivate
AUTH actions, rewrite fixed-service memberships, or replace operational
scheduler suspension. Product reads and mutation classes are separate.
Checker revision routing is allowed wherever checker completion is allowed
through `revision_cutover_fenced`, then denied from `admission_fenced`; it creates
no preparation. Human Review preparation remains inside the already leased
decision command.

### D27 - Oversized Parent Contracts Are Non-Executable

Parents 02A, 03, 04, 05, 06, 07, 09A, 11, 12, 12A, and 13 are split records. Only
the unique children in `CHUNK_MAP.md` may receive future implementation
contracts. Chunk 08 is pure contracts/validation only; chunk 10 is the first
canonical Review/FinalAcceptance/CON commit. Active release docs and router
registration occur together only in 13C.
