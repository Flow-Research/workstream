# Review And Revision Lifecycle

## Status And Authority

This document is the active normative implementation contract for the planned
Workstream v0.1 human review and revision lifecycle. The lifecycle described
here is not yet available in the production API. Each owning REV chunk must
merge hidden behavior, AUTH must activate the exact registered actions, and
`WS-REV-001-13C` must pass the joint release gate before any surface is exposed.

The [Commitrail engineering index](../.commitrail/INDEX.md) identifies the next
durable REV boundary. The canonical action-custody contract owns current
REV-AUTH integration and activation order. This contract defines product
behavior and subsystem boundaries; it does not itself
implement a route, database table, job, authorization evaluator, artifact
capability, contribution participant, or frontend.

The canonical REV-AUTH action custody is
`engineering/review_authorization_action_custody.md`.
REV owns lifecycle and immutable policy semantics; AUTH owns evaluation, PREP,
and decision evidence. ReviewPolicy and RevisionPolicy use immutable,
append-only identities installed by XINT-003-02A; their only writer is the
guide-bound PREP mutation surface activated by XINT-003-02B. This configuration
surface does not activate review queues, leases, findings, decisions, or
revision execution. XINT-002-07A is planned to activate reviewer packet
materialization only; it is not live. ART review-evidence binding remains planned/unavailable and 07B is
reserved pending separate REV-owned intent.

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

### Shared acceptance boundary

The accepted product direction uses `human_review_required: bool = true` in
the existing guide-bound ReviewPolicy. After required post-submit checks pass,
true requires human review; false proceeds through authorized FinalAcceptance
and submitter contribution, without a reviewer contribution. No separate mode
enum, policy entity or adjudication setting is introduced. The
[shared acceptance contract](#finalacceptance) below defines both triggers;
queue, lease and human-decision sections apply only to the human branch. The
[policy setting](../.commitrail/changes/pre-review-plan-reconciliation.md#delivered-policy-setting-implementation)
is persisted and versioned; false activation remains unavailable.
The distinct `requires_second_review` field is fixed to `false` at policy input,
immutable lineage and PostgreSQL boundaries. It does not activate another
review decision or adjudication path.
The hidden source-neutral CON submitter participant and complete frozen award-set
port are delivered. REV-04C now composes one source-neutral FinalAcceptance,
TASK accepted/completed effects and that CON outcome inside the caller's root
transaction. This is a hidden mechanical participant, not the complete
authorized `SharedFinalAcceptanceOperation`: no production authority, routing
handler, currentness guarantee or route is implemented or enabled. In particular,
`allow_review` retains its human-admission meaning, and a checker pass alone
does not authorize FinalAcceptance. No synthetic human Review or ReviewLease
may be used for the false branch.

The human-review shipping branch is:

```text
Project Guide -> Task -> Pre-Submission Intake -> Immutable Submission
-> Post-Submission Evaluation -> Checker admission -> Human Review
-> Revision or FinalAcceptance -> ContributionRecord
-> conditional CompensationAward -> asynchronous external fulfillment
```

Human review decisions are exactly:

- `accept`
- `needs_revision`
- `reject`

Adjudicator project grants and adjudication are excluded from v0.1. No
adjudication action, queue, lease, policy,
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
Separate `submitter` and administrative grants do not substitute.
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
-> verify canonical admission's Submission-stamped ContributionPolicyVersion, copy it
   to ReviewLease.reviewer_contribution_policy_version_id, and append ReviewLease plus
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

Before REV lifecycle implementation begins, `WS-XINT-003-02D` publishes the
closed typed action/resource manifest in
`app.modules.authorization.review_contracts`. REV composers target those exact
strict frozen scalar contracts after locking canonical rows. The manifest is
not an evaluator and activates nothing; it contains neither REV repositories
nor product rules. Later XINT waves connect the already-published family to the
existing PREP/kernel path only after matching hidden REV behavior exists.
Adding a new action, principal, protocol, or resource-context family requires a
planning amendment rather than an ad hoc REV implementation change.

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
- future `ReviewEvidenceArtifact` only if separately approved; not v0.1
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

`requires_second_review` is a canonical false value in the ReviewPolicy body so
existing false-policy hashes remain stable; true is unsupported and cannot be
persisted.

Each policy version has its own opaque ID, positive generation, canonical
SHA-256 digest, and exact Project Guide lineage. The Project Guide selects one
review-policy identity and one revision-policy identity. A Task copies both
exact identity triples when it enters screening; every Submission and
CheckerRun then copies and foreign-key chains those same triples through the
Task. Guide version identifies guide lineage only and is never used as a policy
version alias.

Rows migrated from the pre-lineage schema are retained as
`legacy_incomplete`. They remain readable for historical explanation but cannot
satisfy readiness or activate future review behavior because no lease or
preference semantics are invented from the removed `sla_hours` field. Policy
rows reject update, delete, and truncate at the database boundary. The removed
`auto_reject_after_limit` value is not lifecycle authority: reaching a revision
limit or deadline blocks preparation and never auto-rejects or auto-closes a
Task.

Project Guide activation binds one `ContributionPolicyVersion`; task readiness
locks it before claimability. TaskAssignment copies that lock, Submission
stamps the exact attempt value, and ReviewLease copies the Submission stamp
without claim-time selection. Project Guide or policy
publication alone changes no existing task, assignment, Submission, or lease.
After a human `needs_revision`, complete-context preparation may atomically
rebase the continuing Task and TaskAssignment for the next submission attempt;
earlier Submission and ReviewLease lineage remains immutable.

## Checker Admission

Only a durable, final, current post-submit CheckerRun outcome of `allow_review`
may admit the exact immutable Submission to human review. Admission records the
exact CheckerRun ID and verified binding facts through the later authority-
hardened TASK-owned canonical `allow_review` routing manifest delivered by the
remaining ARCH-04E sequence. The manifest binds the
current evaluation generation/result and immutable Submission; it does not
replace CHECKERS truth or grant review authority. REV validates the current
TASK handoff through its public port before recording admission. A retry, supersession, or
different Submission cannot silently replace that anchor.

ARCH-04E2-A's true-branch preparation binds only TASK's future manifest and
`evaluation_pending -> review_pending` transition. It does not create a REV queue
entry or make REV admission a prerequisite of the TASK transition. Its false
branch instead binds the exact `TaskAcceptedEffectsRequest` for the future shared
FinalAcceptance operation, with no Review, ReviewLease or reviewer contribution.
The routing action remains planned/unavailable and neither branch is executable.

Checker routing is not human judgment. A final needs-remediation CHECKER result
is consumed by the TASK-owned ARCH-04F handler, which moves the Task to
contributor-readable `needs_revision` in its own authorized transaction while
retaining the Task's locked context. CHECKERS does not mutate TASK directly.
This creates no Review,
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

REV consumes only narrow ART-owned typed product capabilities. It never imports
the raw byte-only `ArtifactStore`, a concrete provider, ART repositories,
`ArtifactScratchManager`, `PreparedArtifact`, `CommittedArtifactSource`, object
keys, provider URIs, scratch paths, receipts, or credentials.

`ReviewPacketManifest` is an immutable REV semantic projection naming the exact
queue entry, lease, versioned Submission, admitting CheckerRun/results, stamped
guide/setup context, original ZIP binding and live guide ingest IDs. Revision
response relations belong with the future revision preparation/response storage boundary. It
stores no bytes, artifact content digest, provider location, signed URL, scratch path,
receipt, or authorization-matrix data.

Future exact lease/packet authorization permits artifact bytes only for the single
Submission packet named by its manifest; an active stored lease alone grants none. Prior, expired, consumed, sibling, later,
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


The [ART-07A1 membership contract](../.commitrail/initiatives/WS-ART-001/WS-ART-001-07A1.md)
defines strict detached types and a type-only async port. REV-03B persists one
immutable metadata packet per exact active, unexpired ReviewLease: the original Submission
ZIP binding and all 1–100 ordered guide documents from the locked activated setup.
Guide members name live `ingest_id` values, not the retained extraction binding
table. Canonical PostgreSQL checks reconcile every owner and the complete declared
set, including committed upload receipts. A semantic digest covers the complete
membership; packet generation equals the lease attempt generation. Packet and
ingest facts reject mutation and deletion; identical replay returns the same ID,
including after expiry, closure or guide supersession. Creation checks the deadline
against PostgreSQL time independently of expiry reconciliation. The caller owns
the transaction.

This delivers storage, not claim, a membership resolver or byte access. Future
canonical-owner reads must construct the complete membership, and byte access
requires separate exact lease/packet authorization and current availability checks.
The current catalogue has no output files; adding those requires an explicit
owner-custody contract, not arbitrary additional packet members.

## Review Notes, Findings, And Revision Responses

A reviewer records exactly one decision (`accept`, `needs_revision`, or
`reject`) plus bounded note/findings related to the exact reviewed immutable
Submission. When revision is required, the contributor may record bounded
response text against unresolved findings and submits one new outer ZIP through
the normal human-review revision path. The ZIP is the revision artifact.

There is no separate reviewer-finding or contributor-response artifact upload
in v0.1. `artifact.review_evidence.binding.create` and related evidence-ingest
actions remain planned/unavailable. Any future evidence-upload lifecycle needs
a separate REV-owned intent and reviewed ART/AUTH contract.

## Delivered Review Source Storage

[REV-04A](../.commitrail/initiatives/WS-REV-001/WS-REV-001-04A.md) persists
complete immutable Review, finding, resolution and completed request metadata.
It provides no production writer, AUTH action activation, CON reviewer participant or
public decision route. Real PostgreSQL storage fixtures are not canonical
product decisions. The transaction below remains mandatory for future runtime.

The stored predecessor is the nearest reviewed ancestor on the same-task
Submission chain; checker-only corrections do not fabricate Reviews. Resolutions
can address only open findings in that Review ancestry. Resolved/not_applicable
findings cannot reopen; every inherited open blocker requires a current
resolution. Accept leaves no blocker open, while needs_revision leaves at least
one. The resulting open blocking set is bounded at 100 so a later Review can
resolve the complete set. Immutable aggregate digests seal complete ordered
children. Stable request digests exclude newly generated record IDs and times.

Finding responses remain with revision preparation storage; no unchecked
preparation identity or separate evidence upload is added here. AUTH-19A reconciles
its inert decision contract with inherited-only unresolved blockers and CON's
exact reviewer ContributionPolicyVersion identity. Genuine originating AUTH
execution, persisted receipt custody and runtime integration remain prerequisites;
these contracts and storage tables do not supply authority.

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

`FinalAcceptance` is one internal immutable REV fact, created by one shared
acceptance operation. There is no public/manual creation API, independent
materialization action, second decision entity or automated acceptance engine.
The hidden REV-04C participant writes this fact and composes TASK/CON effects;
both authorized runtime branches remain unavailable.

| Trigger | Required source | Result |
|---|---|---|
| Human `accept` | Authorized `review.decision`, actual Review/ReviewLease, locked `human_review_required=true` and valid admission | Shared acceptance plus the actual Review's reviewer contribution |
| Required post-submit checks pass | Authorized `task.post_submit.route`, exact current routing manifest and locked `human_review_required=false` | Same shared acceptance; no Review, lease or reviewer contribution |

Both produce Task `accepted`, TaskAssignment `completed`, FinalAcceptance,
one submitter `accepted_submission` and applicable frozen-policy awards in
one transaction with authorization evidence, audit and outbox. No post-commit
job repairs missing canonical contributions. Human `needs_revision` or
`reject`, failed checks, unsupported requirements and infrastructure errors
cannot invoke this operation.

Required lineage is:

```text
id
project_id
task_id
submission_id
source_review_id
acceptance_source
source_routing_manifest_id
authorization_decision_event_id
accepted_submitter_id
accepted_at
recorded_by
policy_context_ref
```

`submission_id` is the existing versioned Submission identity.
`accepted_submitter_id` is the canonical human ActorProfile on the Submission
and TaskAssignment. `recorded_by` identifies the canonical AUTH actor of the
originating allow: the reviewer for human acceptance, the admitted fixed TASK
routing service for checker-policy acceptance; never a fabricated human.
`policy_context_ref` identifies the immutable
ReviewPolicy governing that Submission.

`acceptance_source` is provenance, not a configurable policy or workflow mode:
`human_review` requires `source_review_id` and forbids
`source_routing_manifest_id`; `task_post_submit_route` requires
`source_routing_manifest_id` and forbids `source_review_id`. The delivered
ARCH-04E1A TASK source identifies the exact Submission, run,
request/generation, final-result and canonical material lineage, but it is not
routing authority. Before runtime REV acceptance may consume it, ARCH-04E1B/04E2 must harden the
same table with mandatory exact route and owner-receipt custody and refuse
retained pre-authority rows. Do not create a second manifest, an
AutomatedDecision table or copied checker results in REV. The later AUTH event
reference binds the exact source, operation, actor and resource; a checker
finalization allow cannot substitute for routing authority.

PostgreSQL enforces the closed discriminator and complete exclusive source
shape, unique task/Submission acceptance, unique non-null source Review or
routing manifest, same-chain project/task/Submission/submitter/policy/source
integrity, and immutability. Human sources must reference an accept Review,
its reviewer, the exact `review.decision` allow for that Review/reviewer/request
and locked true policy; checker sources must reference the successful manifest governed
by the same locked false policy. FKs plus owner-controlled constraint/trigger
proof must reject direct-SQL crossed sources, not merely nullable fields.
AUTH admission and currentness remain transaction-time checks, not authority
inferred from a FK. v0.1 has no reopen or replacement acceptance.

### Delivered storage foundation and required authority hardening

[REV-04B](../.commitrail/initiatives/WS-REV-001/WS-REV-001-04B.md) delivers one
immutable `final_acceptances` table and closed metadata inputs, with exclusive
Review/TASK source lineage, exact locked policy and submitter, database-owned
time and unique terminal source identities. It adds no writer, reader, shared
operation or TASK effect. Direct SQL fixture rows prove relational
custody only; they are not authorized acceptance. That describes the REV-04B
slice itself; REV-04C is the later hidden
writer/participant described below.

[CON-07](../.commitrail/initiatives/WS-CON-001/WS-CON-001-07.md) delivers the
hidden source-neutral submitter participant and complete frozen award-set port.
After acquiring the supplied canonical REV fence through a CON-owned Protocol,
it stages or exactly replays one accepted-submission contribution and zero, one
or two awards inside the caller's existing root transaction. Exact source
replay returns the original row IDs. Compensated replay requires the original
correlation UUID; unpaid replay retains no correlation. It does not write
FinalAcceptance, change TASK, evaluate AUTH, publish a source, fulfill an award
or create a reviewer contribution.

[REV-04C](../.commitrail/initiatives/WS-REV-001/WS-REV-001-04C.md) delivers the
hidden source-neutral participant over those foundations. With a preallocated
acceptance ID and exact source/generation envelope, it locks the shared fence,
locks and validates TASK without mutation, validates the stored source, appends
or exactly replays FinalAcceptance, applies TASK accepted/completed effects, and
invokes CON with the enclosing create/replay disposition.
It flushes inside the caller's root transaction and rejects partial replay; it
does not commit, authorize a trigger, route a result, stage shared audit/outbox,
create reviewer participation or activate either branch.

`authorization_decision_event_id` above remains a required runtime field, absent
from this foundation because neither originating authority is live. Before any
production consumer, evolve this same strict participant input to require the
exact AUTH decision event, with no optional/default compatibility path, and
harden this same table with a NOT NULL exact AUTH event plus
source/action/actor/request/resource checks. Human authority is the exact
`review.decision` allow; automated authority is the exact fixed
`workstream.task.post_submit_router` actor and `task.post_submit.route` allow.
Service actor kind alone is not provenance. The migration must refuse any
retained pre-authority rows unchanged, never backfill or delete them.
`test_acceptance_authority_upgrade_refuses_retained_foundation` and
`test_acceptance_authority_upgrade_empty` are mandatory future activation proof.

Current automated proof covers closed metadata and a transactionally rolled-back
branch-predicate probe over real true-policy sources. It does not fabricate a
false-policy activation, a router identity or a Review. Positive false-policy
ancestry and the full authorized transaction remain required before activation.

### Shared transaction and dependency direction

REV-04C supplies the hidden transaction participant that appends the REV
acceptance fact and invokes TASK's accepted/completed-effects port plus CON's
existing submitter participant. At 04E2-B the same participant input/schema must
evolve to require the verified AUTH event, without an optional/default path, and
the complete `SharedFinalAcceptanceOperation` must stage shared audit/outbox
effects. Both callers invoke that same evolved public operation, not copied
sequences. CON validates the fact and
exact assignment before appending the contribution and conditional awards.
All participants flush only. The initiating command owns the single commit: human decision
composition also stages the actual Review and reviewer contribution; TASK
post-result composition instead stages the routing manifest. Neither owner
imports the other's private service or implements a competing orchestrator.
REV's acceptance operation consumes locked typed source facts supplied by
composition and TASK's narrow effects port; it does not call back into TASK
routing. CON consumes acceptance
and assignment facts and never calls the originating command. This prevents a
TASK routing -> REV decision -> TASK routing dependency cycle.

The false branch reuses `workstream.task.post_submit_router` and the proposed
`task.post_submit.route` contract; its allowed derived effects explicitly
include this shared acceptance sequence only for the false/pass case. This
does not grant `review.decision`, a generic CON write, checker execution or
dispatcher authority. AUTH owns registration, exact resource/PREP validation
and activation; missing or unavailable authority fails closed.

Acquire the shared lifecycle/obligation fence before owner state locks, then
lock TASK Submission/current routing state before the CHECKERS currentness
fence using existing ARCH-04E order. Revalidate the exact locked guide,
ReviewPolicy, contribution-policy/assignment lineage, complete successful
required-check evidence and all required output bindings before staging
acceptance. For false, the exact approved requirement inventory must contain
zero applicable `human_review` dispositions, both at guide activation and
again at acceptance. Such a disposition is not a failed executable check and
cannot be silently relabeled `supported_post_submit` or ignored because all
executable checks passed. Never read the project's newest policy to choose the branch.
ARCH-04E1B-B1 enforces TASK-before-CHECKERS custody for reservation and
current-result reads. Review queue/admission INSERT guards acquire the exact
project-qualified TASK before checker fences and foreign keys. Admission UPDATE
does not acquire TASK after its own row lock; composite admission callers start
with the guarded current-result read. PostgreSQL proof includes the intermediate
wait between that read and queue insertion, not just completed admission. Its
PostgreSQL controls prove that shared acceptance prevents a later generation,
and a committed successor invalidates old routing preparation. The complete
authorized routing/acceptance race remains 04E1B-B/04E2-B proof; these hidden
controls do not activate either trigger. After acceptance,
reject a new evaluation generation, resubmission or policy
rebase for that task. Racing acceptance, supersession and retries serialize:
an earlier supersession rejects old evidence; an earlier acceptance prevents
supersession from invalidating terminal truth. Exact duplicate delivery returns
the same outcome; a changed envelope under the same identity denies.

### Implementation order and required proof

Extract foundations from existing owner work, not a new initiative:

1. ARCH-04E1A's TASK manifest persistence/detached scalar facts and narrow
   accepted-effects Protocol are delivered after CHECKERS-04C facts, without a
   general routing publication writer/reader, current pointer or handler. Its
   bounded exact-source verifier is used by REV-04C. One manifest stores the locked `human_review_required` branch; it is
   not restricted to human admission. False proof is scalar transport only
   while activation remains unavailable. This schema precedes the REV source FK.
2. [ART-07A1](../.commitrail/initiatives/WS-ART-001/WS-ART-001-07A1.md) supplies
   the metadata-only packet contract. REV-03B normalized packet persistence is
   delivered. REV-04A immutable Review-source storage and REV-04B shared FinalAcceptance
   storage and CON-03C contribution/award persistence are delivered. Do not create
   an incomplete Review solely as an FK target. REV-12A1 supplies the disabled
   controller and transaction fence. Exact hidden AUTH preparation, CON-07
   participation and REV-04C hidden FinalAcceptance/TASK/CON composition are
   delivered; mandatory persisted receipt custody precedes production composition
   or consumption. These foundations require no live human claim or
   decision endpoint. Hidden composition proof precedes exact AUTH
   activation; unavailable authority must not be replaced with fabricated allow evidence.
3. [REV-12A1](../.commitrail/initiatives/WS-REV-001/WS-REV-001-12A1.md)
   delivers disabled generation-zero controller storage and the caller-root
   transaction fence. AUTH-19A supplies inert exact source/request and detached receipt contracts.
   ARCH-04E1B-A delivers distinct routing-request and future source-ID reservation.
   ARCH-04E2-A delivers the hidden `task.post_submit.route` strict resource and
   preparation matcher plus nominal `workstream.task.post_submit_router` adapter
   through canonical PREP. The action remains planned/unavailable and denial occurs
   before handle issuance; no allow, receipt, source publication or effect exists.
   CON-07 then delivers the flush-only participant and complete frozen award-set
   owner. Its consumer-owned Protocol acquires the supplied canonical fence
   before CON or compensation access; exact source replay preserves contribution
   and award IDs, paid replay checks correlation, and unpaid replay retains no
   correlation. REV-04C composes those effects with FinalAcceptance and TASK
   accepted/completed effects for either source. These isolated controls prove
   mechanical transaction behavior without claiming acceptance authority or
   fabricating allows.
   REV-12A4A supplies authorized transitions and atomic writer/stop composition
   on this fence before the first contribution path. Applicable award facts remain atomic. Actual
   CON fulfillment roots own immutable ordinal allocation before fulfillment
   admission is enabled; no award or outbox row substitutes for a root. Payment
   obligation storage and its root/cutoff proof are not prerequisites of a
   manifest that keeps fulfillment admission, dispatch and callbacks unavailable.
4. ARCH-04E1B-B's hidden routing handler is next and invokes the delivered
   participant for false/pass. It owns TASK-before-CHECKERS currentness and both
   successor-generation race orders. True routing does not
   require CON or shared acceptance; it uses the delivered preparation, hidden 04E1B-B, exact
   AUTH 04E2-B and live 04E3 after its own prerequisites. The existing lifecycle-control command receives
   scoped AUTH activation for the proven shared manifest as specified below;
   ARCH-04E2-B evolves the same strict participant input to require the exact
   AUTH decision-event receipt, with no optional/default path; installs
   mandatory same-table receipt custody and database-enforced complete-set
   closure across FinalAcceptance/TASK/CON; stages shared audit/outbox; and
   activates the existing action. Its first genuine allow commits in one caller transaction
   with source publication, FinalAcceptance, TASK effects, CON rows and audit/
   outbox; failure rolls all back. Retained pre-authority sources remain refused.
   ARCH-04E3 then proves live composition.
   PROJECTS enables false only after that
   proof and ARCH-04F's usable checker-remediation path.

These are dependency slices of existing work, expanded into bounded records
when implemented, not an extra planning-approval loop. Do not make the early
manifest schema depend on its later handler or the early shared fence depend
on live human review. Human runtime later adds its decision/lease proof and
reuses the same operation. Fulfillment/read endpoints remain downstream.

Remaining implementation tests:

| Owner / future test | Required discriminating proof |
|---|---|
| REV `test_final_acceptance_source_constraints` | Direct SQL rejects both/neither source, unknown discriminator, wrong project/policy, non-accept Review, false-policy Review source and true-policy checker source; rejects reviewer/recorded_by mismatch, human event not the exact review.decision allow for that Review/reviewer/request, manifest service/AUTH-event mismatch, wrong submitter vs Submission/Assignment, and crossed same-project/policy manifest; valid sources persist |
| TASK `test_post_submit_false_uses_shared_acceptance` | Real composition with true/false locked controls, same FinalAcceptance/CON participant, and no Review/lease/reviewer contribution on false; passing checks plus an approved human_review disposition denies with zero effects |
| TASK `test_acceptance_races_supersession_and_redelivery` | Independent sessions in both orders; one terminal acceptance and no stale run, duplicate award or invalidated accepted history |
| AUTH `test_post_submit_route_acceptance_custody` | Wrong service/action/resource, unavailable authority, copied event and wrong transaction deny before product effects |
| REV/AUTH `test_shared_acceptance_lifecycle_activation_and_drain` | Same registered Operator command establishes a generation through legal adjacent transitions; real enabled-writer observations, cutoff races, restart and safe stop; fabricated zero observations, unlisted writer or human-surface exposure denies |
| CON `test_shared_acceptance_atomic_rollback` | Fail after staged task/acceptance/contribution/award/audit/outbox writes; every row/effect rolls back in both branches; valid control commits once |
| PROJECTS `test_false_activation_requires_supported_acceptance` | An approved human_review requirement disposition, missing required output contract or unavailable shared composition blocks activation; no silent reclassification; supported complete configuration activates only after runtime proof |

Proposed test homes are `backend/tests/test_shared_final_acceptance.py` (REV),
`backend/tests/test_task_post_submit_routing.py` (TASK),
`backend/tests/authorization/test_post_submit_route.py` (AUTH),
`backend/tests/contributions/test_shared_acceptance.py` (CON), and the existing
`backend/tests/projects/test_activation_readiness.py` for PROJECTS. Run each through
`cd backend && uv run pytest <test-file> -k <test-name>` with real PostgreSQL;
`<test-file>` is relative to `backend` (for example,
`tests/test_shared_final_acceptance.py`, not `backend/tests/test_shared_final_acceptance.py`);
the full unchanged hosted suite/coverage remains required for implementation.
These are future files/tests. Implementation records resolve exact paths
against then-current main and retain the behavior/proof obligations, not invent
another acceptance architecture.

## Contribution And Compensation Boundary

`docs/spec_contribution_compensation.md` and ADR 0016 are the canonical CON
contract authority. This section defines REV's orchestration obligations at that
boundary. Merged CON-01 publishes contracts only; it implements no policy
persistence, contribution record, award, participant, or fulfillment runtime.
CON-07 delivers the source-neutral submitter port and complete frozen award-set
owner; REV-04C composes its submitter path with hidden FinalAcceptance/TASK
effects. Reviewer participation and authorized runtime composition remain future.

Every committed Review creates exactly one reviewer `completed_review`
ContributionRecord sourced directly from the Review and ReviewLease. Only
FinalAcceptance creates a submitter `accepted_submission` ContributionRecord.
CON never infers submitter acceptance from `Review.decision`.

The target CON boundary exposes two operation-specific flush-only inputs:

- reviewer input for every decision, containing Review, ReviewLease, reviewer,
  lease-frozen ContributionPolicyVersion, Submission/project/task lineage,
  AuthorizationDecision, request/correlation references, and stabilized
  `artifact_hash`; it contains no FinalAcceptance or submitter-policy facts;
- delivered submitter input only after accept creates FinalAcceptance and applies
  accepted task effects, containing immutable scalar FinalAcceptance,
  TaskAssignment, submitter, assignment-frozen ContributionPolicyVersion,
  stabilized artifact, correlation and expected-generation facts. It carries no
  authorization decision or receipt-shaped authority value. Before production
  consumption, the enclosing REV participant input must separately require the
  exact AUTH decision-event receipt; this absence is not an optional authority path.

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

Revision preparation compares the prior Submission's complete stamped context
with the project's complete currently active applicable guide and policy
context:

- exact component identity/version/activation match: `kept`;
- every changed internally consistent active component: `rebased` together,
  recording `forward` or `backward` where applicable, including intentional
  reactivation of an older version;
- any missing, incomplete, revoked, internally inconsistent, crossed-project,
  or unsafe active component: the whole context is `blocked` for covered
  Project Manager repair.

Version strings are never ordered. Activation sequence records chronology but
does not overrule which guide is currently active.

`RevisionContextPreparation` is immutable and rooted in the exact
`needs_revision` Review and prior Submission. It freezes the complete selected
next-attempt guide/source, submission/checker, review, revision,
task-template/task-execution, and submitter ContributionPolicy context; context
digest; outcome; direction; change summary; source and target TaskAssignment;
preparation sequence; preparing actor/process; and audit link. It records prior
and next ContributionPolicyVersion lineage and, when changed, atomically
updates the continuing Task and TaskAssignment for the next submission attempt.
The prior Submission and completed ReviewLease remain immutable.

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

The needs-revision Review and its reviewer contribution/award use the completed
ReviewLease's frozen policy. The next Submission uses the complete newly
prepared task context and stamps its policy version; its next ReviewLease
copies that immutable Submission value. Accept and reject perform no rebase. The Review, reviewer
contribution/award, task and assignment effects, initial preparation or blocked
outcome, audit/outbox effects, and contributor-visible state commit once or
roll back together.

## Finding Replay And Resubmission

For a human-review origin, every unresolved blocking ReviewFinding requires one
immutable `SubmissionFindingResponse` from the assigned submitter, with bounded
response text. Responses to advisory findings are optional unless the locked
policy explicitly requires them. The checker-remediation path instead exposes
only bounded contributor-safe CheckerResult messages/suggested fixes, requires
no fabricated ReviewFinding/response/resolution, and returns to open routing
after corrected checker admission.

A human-Review Submission N+1 links its immediate predecessor, exact preparation
head, required bounded response text, and target TaskAssignment. A
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
activate a review action or provision any of REV's six registered service identities.

The pre-WS-XINT-003-02C review lifecycle baseline identified 24 unavailable
actions:

- registered planned `submission.create`;
- 19 registered planned review actions; and
- four then-unregistered approved REV actions, now registered but unavailable,
  defined below.

The registered planned `artifact.review_evidence.binding.create ->
artifact.binding.create` service action is separate, unavailable, and not one
of the 24. It has no approved v0.1 activation. Future counts must be derived
from trusted main at each AUTH gate.

The current exact delivery order is:

```text
WS-XINT-003-02C complete unavailable catalogue/principal/matrix readiness
-> WS-XINT-003-02D complete fail-closed PREP/read contract readiness
-> REV hidden behavior and canonical composers plus required ART/CON capability
-> exact XINT evaluator integration and action-by-action activation
-> REV-13C joint product-surface release
```

Historical `WS-AUTH-001-REV-CUSTODY` transferred the 19 registered planned
review rows without changing availability, and `WS-AUTH-001-PREP` supplied the
prepared mutation protocol. Historical aliases `WS-AUTH-001-REV-REG`,
`WS-AUTH-001-REV-05/06/07/08/09A/11/12`, and
`WS-AUTH-001-REV-LIFECYCLE` are superseded as delivery authority by canonical
WS-XINT-003 custody. 02C registers the four additions unavailable; 02D publishes
their fail-closed contracts; later exact XINT waves activate only merged hidden
behavior. REV-13C alone exposes the coherent product surface.

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
ActionId membership. None exists on the trusted pre-02C baseline.
WS-XINT-003-02C installs the reviewed enum/database-constraint/static-matrix
extensions and controlled admission while every action remains unavailable;
02D publishes the fail-closed contracts. Cross-service/human denial and later
exact action activation remain mandatory. No catch-all review service exists.

| Fixed service identity | Exact ActionId | PermissionId | Hidden consumer | Activation gate |
|---|---|---|---|---|
| `workstream.review.preference_expiry` | `review.preference_expiry.run` | `operations.timer.run` | REV-06C | `WS-XINT-003-03D` |
| `workstream.review.lease_expiry` | `review.lease_expiry.run` | `operations.timer.run` | REV-06C | `WS-XINT-003-03D` |
| `workstream.review.authority_invalidation_reconciliation` | `review.reconcile.run` | `operations.reconcile.run` | REV-11C | `WS-XINT-003-08B` child |
| `workstream.review.reconciliation` | `review.reconcile.run` | `operations.reconcile.run` | REV-11C | `WS-XINT-003-08B` child |
| `workstream.review.artifact_reference_reconciliation` | `review.artifact_reference.reconcile` | `operations.reconcile.run` | REV-12P2 | `WS-XINT-003-08B` child |
| `workstream.review.projection` | `review.projection.rebuild` | `operations.projection.rebuild` | REV-12P2 | `WS-XINT-003-08B` child |

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
- reviewer note/findings and bounded contributor response text;
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

### REV-12A shared fence foundation

REV-12A is a historical non-executable split record. Its shared persistence/fence foundation is delivered by REV-12A1; actual CON
root ordinal custody remains with the future root owner, as specified in the
[shared implementation order](#implementation-order-and-required-proof).
Later REV-12A transition, drain and Operator slices extend, rather than recreate,
that one PostgreSQL-canonical `JointLifecycleReleaseControl`. They add
compare-and-set phase history,
PostgreSQL advisory-lock fences, mandatory typed fence ports, and bounded drain
observations across review mutations, task submissions, queue admission,
authority-loss replacement, CON fulfillment-obligation writers, dispatch, and
callbacks.

REV-12A1 stores one immutable disabled generation-zero controller and supplies
an advisory-before-row fence within the caller's active root transaction.
Before either lock, a native `pg_catalog.pg_export_snapshot()` call rejects
raw-SQL savepoints as well as managed subtransactions, while permitting prior
AUTH/idempotency queries. Its identifier is discarded, never exposed or retained
as product data; PostgreSQL holds the temporary snapshot (including xmin) until
transaction end. Callers keep transactions short, retain commit/rollback ownership
and roll back after acquisition failure. PostgreSQL two-phase prepare is unsupported.
Savepoints established after acquisition cannot release the earlier root locks. Its
public scalar facts are not authority. The current AUTH activation resource
binds a strict transition command and observations; generation zero must be
disabled. Other inert REV resources retain their own phase projections. The four phases are disabled, shadow, live and draining. Detailed
shutdown stages in historical plans are not additional current persisted phases.

REV-12A1 alone implemented no transition or usable generation. REV-12A4A now
extends it with Operator-authorized legal adjacency, immutable history, exact
AUTH/controller closure and current-generation read-only replay. Transitions take
the REV fence before AUTH control and principal locks; acceptance takes REV
before TASK, and task reads take TASK before AUTH. Controller mutation refreshes
any cached ORM state from the already locked database row. It does not
activate an acceptance consumer or fulfillment. Actual CON root storage and
real authorized writer-versus-cutoff proof are required before a successor
manifest activates fulfillment admission, dispatch or callbacks. They do not
block the first contribution manifest with fulfillment disabled. Lock mechanics
alone do not prove asynchronous drain correctness. Both acceptance callers require
a valid authorized lifecycle generation, without a bootstrap bypass or second
availability flag.

### Scoped activation before human-review runtime

The existing registered Operator action `review.lifecycle.activation.manage`
and its `ReviewLifecycleActivationContract` establish the first usable
generation through the same legal adjacent transitions. Pull the corresponding
REV-12A transition/recovery slice and AUTH XINT-003-08B activation forward after
hidden shared-acceptance proof, rather than waiting for human review endpoints.
The resource still binds singleton, expected generation, phases, operation,
reviewed manifest and observation digests, deadline and reason. No SQL bootstrap,
new action, permissive default generation or second availability flag is allowed.

The first-contribution manifest covers its enabled TASK admission/routing and
shared acceptance/CON contribution and conditional award writers. Payment
obligation admission, dispatch and callbacks remain unavailable; their absence
must be checked against actual composition, not represented by fake zero drain
counts. Paid and unpaid contribution policies retain their full atomic award
semantics. Neither payment delivery nor its obligation/root/ordinal substrate
is a prerequisite of this bounded manifest.

The initial controller implementation is
[REV-12A4A](../.commitrail/initiatives/WS-REV-001/WS-REV-001-12A4A.md).
It extends the same Operator action, singleton and fence;
it does not grant routing or acceptance authority. Every enabled writer must
appear in its reviewed manifest. Server-derived observations are checked under
the canonical lock. Unsupported surfaces and unlisted writers deny. Human
queues/leases/decisions and fulfillment remain unavailable. Retained mechanical
acceptance facts cannot establish missing originating AUTH receipts.

For atomic participants, the shared transaction fence waits for earlier writers;
a phase change prevents later new effects. Exact terminal replay compares retained
facts without new writes, using the current generation as the fence precondition.
When asynchronous routing is enabled, its successor manifest must prove actual
admitted-work drain and crash recovery before activation. No generic drain system
or fabricated observation is required for absent asynchronous participants.

The same authorized Operator command is shared infrastructure, not a reviewer
endpoint or contributor approval step. Later human/fulfillment release adds its
actual observation/custody proofs under the same controller and action.
Before fulfillment admission is enabled, CON must own real immutable roots and
ordinals. Shutdown then drains prior writers and captures the server-derived
cutoff, permits only same-generation pre-cutoff completion, and disables only
after the governed drain. None of those future operations is implied by storing
an award fact.

Activation and shutdown are generation-bound and crash resumable. Timeout leaves
the phase unchanged for forward retry. No background job replays human Operator
authority or advances a phase. Reactivation verifies the reviewed manifest and
current observations; an expanded scope requires a reviewed successor manifest.

This controller is product release state, not AUTH action availability. The
full human 12A1 through 12A4 implementation expands the shared foundation;
its full management/drain manifest is activated and drilled by REV-13C only
after all required hidden behavior merges. It does not revoke the earlier
bounded shared-infrastructure activation or silently widen that manifest.

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
selection, claim/release/expiry, active-lease packet access, note/findings,
`needs_revision`, kept/forward/backward/blocked preparation, response/resolution
replay, preferred return and takeover, accept with exactly one FinalAcceptance,
reject, reviewer revocation, manager repair and closure, legacy recovery,
provider outage/integrity failure, transaction rollback, contribution/award
source integrity, outbox retry, projection recovery, shutdown, crash resume, and
coherent reactivation.
