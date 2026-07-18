# Plan: WS-REV-001 Review And Revision Lifecycle

## Approach

Build the lifecycle as one review-owned backend module integrated with existing
tasks, submissions, checkers, audit, authorization, artifact, job execution, and API
composition boundaries. Land persistence before behavior, keep every public
mutation hidden until its invariants and cross-domain participants exist, and
use PostgreSQL constraints as final race guards.

## Dependency gates

### Authorization gate

Merged WS-XINT-001 and AUTH reconciliation PR #140 fix one delivery protocol for
every protected REV surface:

```text
AUTH planned registration and activation-custody assignment
-> required ART/CON capability plus REV hidden behavior and canonical facts
-> AUTH evaluator integration and exact action activation
-> REV joint product-surface release
```

REV never registers an ActionId, edits `ActionOwner`, integrates an AUTH
evaluator, or changes action availability. A REV feature chunk owning hidden
behavior and resource facts produces lifecycle guards, a canonical typed
ResourceContext composer, and a feature-manifest delta while the real kernel returns
`action_unavailable`. AUTH alone activates the action after that evidence and
all required hidden participants merge. REV-13 exposes only already-active
surfaces after a separate joint readiness check.

PR #140 changes planning only. Merged AUTH-09A PR #132 now provides the common
fixed-service enum/schema/migration and the closed seven-identity ART matrix,
but it activates no action, provisions no actor, admits no service token, and
does not add REV's six identities. `WS-AUTH-001-REV-CUSTODY` must first transfer all
19 registered planned review actions to seven exact AUTH activation custodians
without changing mappings, counts, or availability. `WS-AUTH-001-PREP` then lands
the shared prepared-mutation runtime. Exact feature gates
`WS-AUTH-001-REV-05/06/07/08/09A/11/12` integrate evaluators and activate only
their merged hidden behavior. After REV-01 publishes the immutable registration
manifest, `WS-AUTH-001-REV-REG` registers the four approved REV additions as
planned; `WS-AUTH-001-REV-LIFECYCLE` activates those additions
only after the REV-11 and REV-12A manifests are complete.

REV-01 turns this reviewed plan into the active contract and publishes two
immutable, availability-neutral inputs before runtime feature chunks: the
complete four-action registration manifest consumed by
`WS-AUTH-001-REV-REG`, and six independent service identity-to-ActionId manifests
consumed by later AUTH identity-specific extension contracts. Those manifests
name required hidden dependencies but do not claim behavior is implemented.
AUTH may register planned actions and define/provision exact REV identity
extensions from the merged REV-01 SHA while REV persistence chunks continue in
parallel. Those extensions build on, and do not replace, AUTH-09A's fixed-service
foundation. Hidden behavior
chunks later emit separate activation manifests; no registration or identity
extension activates an action or exposes a product surface.

Merged AUTH-08 PR #131 establishes the current public kernel and resolves the
three AUTH-07B consumption blockers. Every runtime chunk retains proof that:

- the reusable authorization dependency never commits a feature-owned open
  transaction during generic successful teardown; every read or mutation owner
  commits its own business-plus-decision unit explicitly;
- SQL failures while staging authorization evidence map centrally to the stable
  retryable service-unavailable response and leave no business mutation or
  partial decision evidence; and
- AUTH documents and restores its canonical `ActorProfile.last_seen_at` and
  `ActorIdentityLink.last_verified_at` semantics for successful existing-actor
  GET/PATCH access, with API regression proof. REV does not prescribe AUTH's
  sequencing or lifecycle-denial timestamp policy.

After the exact owning AUTH gates merge, WS-REV consumes:

- canonical actors: every human lifecycle FK stores the active canonical
  `ActorProfile.id`; external issuer/subject, email, legacy profile row IDs,
  token roles, and contributor profile labels never substitute for actor
  identity;
- one exact active project `reviewer` grant for human review. Separate
  `submitter`, `adjudicator`, and administrative grants never substitute, and
  revoking reviewer authority never mutates another grant;
- exact REV identity extensions, controlled provisioning through merged
  AUTH-09B, and AUTH-09E fixed-service admission for protected jobs.
  Preference expiry, lease
  expiry, reviewer-authority invalidation reconciliation, general review
  reconciliation, artifact-reference reconciliation, and projection rebuild
  use distinct immutable service identities and exact static ActionId rows,
  never a generic service, human reviewer, or Operator fallback;
- exact service identities are registered only after REV publishes each
  identity-to-ActionId manifest; generic AUTH-09E admission does not pre-create a
  catch-all review service or make a later identity extension executable;
- 24 non-executable review-lifecycle action dependencies: registered planned
  `submission.create`, 19 registered planned review actions, and four approved
  but unregistered REV actions for revision closure/recovery and joint release
  control. The separate ART evidence-binding action is not one of the 24;
- AUTH-14 activation of `submission.create` only after merged REV-09A prepared
  revision/replay behavior, exact final-fact recomposition, and initial/revision
  API proof; this action is a required REV-13 release gate alongside the named
  review activations;
- `review.revision_context.repair` maps to existing PermissionId
  `project.task.manage`, a covered Project Manager candidate, and an exact typed
  task/assignment/prior-Submission/episode/head resource with transaction
  revalidation;
- `review.revision_context.legacy_close` maps to existing PermissionId
  `operations.reconcile.run`, an Operator AdminRoleGrant candidate, and an exact
  typed unresolved reconciliation-finding/project/task/no-Review/no-root
  resource with transaction revalidation;
- `review.revision_obligation.close` maps to existing PermissionId
  `project.task.manage`, a covered Project Manager candidate, and the exact
  task/assignment/needs-revision Review/current preparation head/observed
  limit-or-deadline resource with transaction revalidation;
- `review.lifecycle.activation.manage` maps to existing PermissionId
  `operations.reconcile.run`, an Operator AdminRoleGrant candidate, and the
  exact singleton control/current phase/target phase/manifest digest resource
  with transaction revalidation;
- registered permissions, with `review.queue.override` as the only additive
  PermissionId;
- canonical resource contexts and project mismatch handling;
- request-scoped `AuthorizationService.require(action_id, resource_context)` for
  reads only;
- the AUTH prepared mutation protocol for writes: AUTH returns an opaque,
  non-Pydantic, single-use `PreparedAuthorizationHandle` bound to the exact
  `AsyncSession`, ActionId, actor-reference kind and ID, idempotency key, and
  canonical request digest after locking current authority. REV locks canonical
  feature rows and recomposes final typed facts, then calls AUTH with those facts
  and the opaque handle. AUTH validates every binding and current authority,
  consumes the handle exactly once, evaluates exactly once, and stages bounded
  decision evidence before the first feature mutation; participants flush; and
  the request route or service command commits once. Binding substitution,
  serialization, caller construction, already-consumed replay, or authority loss
  denies before feature mutation;
- immutable authorization decisions and audit links;
- revocation invalidation used to recover active review leases.

Prepared-handle protocol rejection and evaluated denial are different outcomes.
An unconsumed handle presented with a wrong session/action/actor/request binding,
or a serialized, caller-constructed, or forged substitute, stages no
AuthorizationDecision/evidence, does not consume the legitimate handle, and
must allow that handle's later exact first use. A stale or already-consumed
handle, including the losing side of concurrent duplicate use, stages no new
decision/evidence or feature state, remains consumed, and can never become valid
again; exactly one concurrent exact consumer may win. When an exactly bound
handle reaches evaluation but current authority or policy denies, the request
route or service command rolls back the dirty caller transaction; AUTH restages
the unchanged bounded denial evidence in a clean transaction; and the request
route or service command commits that evidence once. No REV/task/ART/CON mutation
or feature/shared audit/outbox effect survives. If denial-evidence restaging
fails, nothing commits.

REV owns its typed ResourceContext composers and lifecycle guards. It imports
the public AUTH service and `ActionId` types only; it never imports AUTH
repositories/models, queries grants, or reconstructs permission unions.
The four additive ActionIds and their closed mappings are registered together by
`WS-AUTH-001-REV-REG`, not review code. Their hidden manifests land in chunks 11
and 12A; `WS-AUTH-001-REV-LIFECYCLE` later integrates their evaluators and
activates them together. They add no PermissionId. The AUTH-08 runtime snapshot
contained 57 actions: 9 active and 48 planned. That is historical provenance,
not a fixed future total. Current trusted main after AUTH-09C contains 65
actions: 12 active and 53 planned. AUTH-09B activates
`actor.service.provision`; AUTH-09C activates only `actor.profile.read` and
`actor.identity_link.read`. Neither adds a REV identity or action, and all 24
REV dependencies remain unavailable.
WS-XINT-001 separately proposes
`artifact.review_evidence.binding.create -> artifact.binding.create` for the
ART binding service. Every later AUTH registration or activation chunk derives
the exact before/after count and SHA from then-current trusted main and proves
typed catalogue, activation custodian, PostgreSQL audit parity, allowed/denied
evidence, upgrade, and unsafe-downgrade behavior. The four REV proposals and the
separate ART service action are never silently combined into a hard-coded total.

### Artifact gate

Artifact-sensitive work starts only after the required WS-ART contracts are
merged and proven. WS-REV consumes:

- immutable ART binding IDs and server commitments;
- a narrow active-lease packet-read capability that revalidates exact packet
  membership and returns a bounded stream;
- ART-owned two-phase evidence candidate/finalize ports for finding and response
  evidence;
- stable verification/availability facts and deterministic projection storage;
- LocalStorage and MinIO conformance with AWS S3 as production provider.

Merged ART-02A2 PR #129 established the committed-source/private-scratch
foundation. Merged ART-02A3 PR #141 at trusted main
`a10d9018007d2e847b4870e9b26cbd24e24c7bb4`, final branch head
`7606798e751abf40218d23886779c3659b76e974`, removes v1 and activates the
byte-only ART v2 LocalStorage clean cut and typed product capability boundary.
`ArtifactScratchManager`, `PreparedArtifact`, `CommittedArtifactSource`, and the
raw byte store are ART-internal mechanics, not REV capabilities or durable
product references; review code never imports or stores them. Later ART-owned
S3/MinIO, submission/checker binding cutovers, admission,
verification/publication, packet read, evidence candidate/finalize, projection,
and live-proof chunks remain hard gates. ART owns candidate retention and
Operator recovery; REV does not consume the raw store,
`artifact.binding.read`, or a generic artifact-retrieval action.

The current merged ART plan does not yet assign two other exact XINT
requirements to an approved owner chunk: a narrow active-lease packet-read port
and server-derived verified `Submission.artifact_hash` persistence in the
submission/checker cutover. Both require ART/task-owner amendments, approval,
and merge before their REV consumers; the existing artifact-set context or
caller `package_hash` is not equivalent. REV does not name a dependency chunk
until the ART owner publishes one.

REV owns immutable `ReviewPacketManifest` and `ReviewEvidenceArtifact` semantic
records. The manifest names the exact queue/lease, versioned Submission,
admitting CheckerRun/results, locked guide/revision context, response-evidence
relations, and ART binding IDs. It contains no bytes, digest, provider reference,
object key, signed URL, scratch path, receipt, or authorization-matrix data.

Evidence binding additionally requires the separately registered
`artifact.review_evidence.binding.create` service action, mapped to existing
`artifact.binding.create` and available only to `workstream.artifact.binding`.
A separately approved `WS-ART-001-REV-EVIDENCE` capability supplies hidden
canonical facts and binding behavior; AUTH alone integrates its evaluator and
activates it. That ART owner chunk is not scheduled by the currently merged ART
plan, so REV-07 remains blocked until ART adds, approves, and merges it together
with an approved packet-read owner contract. No Operator read action or generic
PermissionId substitutes.

### Contribution gate

Merged CON-01 at `e118e33afcd89b8ee78ecfc8f0e0d585ae0ee4b9` publishes
`docs/spec_contribution_compensation.md` and ADR 0016 as the canonical CON
boundary. They require FinalAcceptance as the sole submitter-acceptance source,
REV-owned decision orchestration and sole commit, ordered flush-only CON
operations, and REV staging of shared audit/outbox inputs returned by CON. The
older WS-XINT `REV_CON_HANDOFF.md` remains historical supporting handoff
material; it no longer outranks the merged CON contract. CON-01 implements no
runtime, so its later persistence, freeze, lineage, and participant chunks still
gate canonical Review composition.

The cross-initiative sequence is explicit:

- AUTH first repairs the circular AUTH-13/14 graph and merges a separately
  reviewed schema-only contributor-field foundation. That foundation performs
  only the canonical TaskAssignment/Submission field clean cuts and preserves
  current behavior; full AUTH-13/14 product cutovers are explicitly later;
- parent `WS-REV-001-02` is a non-executable split record. After the exact
  AUTH foundation merge, 02A establishes guide activation chronology and Task
  stamps, 02B establishes immutable review/revision policy plus dormant
  task/assignment compatibility, and 02C establishes immutable
  `Submission.task_assignment_id` attribution and lineage;
- WS-CON's approved replacement chunks then freeze submitter
  `ContributionPolicyVersion` on `TaskAssignment` and remove legacy
  compensation-context fields and
  consumers before `WS-REV-001-09A`;
- merged WS-CON contribution-policy persistence precedes `WS-REV-001-03`, so
  ReviewLease FKs target a real owner;
- merged shared outbox persistence and caller-transaction lifecycle audit
  participants precede `WS-REV-001-04`, where REV adds immutable
  `FinalAcceptance` persistence beside Review;
- the WS-CON ReviewLease freeze capability precedes `WS-REV-001-06`;
- REV-04's `FinalAcceptance` schema and REV-09B's stable lineage precede CON's
  exact source-lineage schema and flush-only contribution/award participant;
- that exact CON participant precedes `WS-REV-001-10`;
- REV-09A's hidden prepared revision/replacement behavior precedes the amended
  full AUTH-13/14 product cutovers and AUTH-14 activation of `submission.create`;
- those AUTH cutovers and activation precede REV-13 product release; and
- the exact WS-CON readiness manifest, mandatory fulfillment obligation-writer,
  dispatch, and callback fence hooks, and same-session fulfillment/outbox
  drain-cutoff and observation port
  precede hidden joint release-control integration in `WS-REV-001-12A`; and
- all matching AUTH actions activate after their hidden behavior, and the merged
  12A controller and fences precede the sole joint product release in
  `WS-REV-001-13`.

Contribution policy context is independent of guide/review execution context. A
forward or backward Project Guide rebase never changes the submitter's frozen
TaskAssignment `ContributionPolicyVersion`. Each new ReviewLease independently
freezes the current reviewer `ContributionPolicyVersion`. Review services do not
implement rules, awards, fulfillment, evidence projection, or provider delivery.

Every valid `review.decision` request appends one immutable Review. Every finding
and resolution submitted with that decision is also appended as an immutable
record. A later review round creates new records; it never updates the history
from an earlier round. After closing the lease and queue entry, the request calls
the reviewer operation on one mandatory typed CON participant. That operation
creates `completed_review` directly from Review and ReviewLease lineage and
evaluates the lease-frozen reviewer rule.

Only after that common reviewer-contribution operation does REV apply the
decision branch. When the decision is `accept`, REV creates one immutable
`FinalAcceptance`, applies accepted Task and TaskAssignment effects, and calls the
participant's submitter operation. That operation creates `accepted_submission`
from FinalAcceptance and TaskAssignment lineage and evaluates the
assignment-frozen rule.
`needs_revision` and `reject` apply their Task and TaskAssignment effects without
FinalAcceptance or the submitter contribution operation.

Both operations belong to the same mandatory participant, use the caller's
AsyncSession, flush without commit, copy the stabilized versioned Submission
`artifact_hash`, and return typed audit and outbox inputs. CON never infers
acceptance from `Review.decision`, calls ART, rederives the digest, or commits.
REV stages the shared audit and outbox rows, and the request route or service
command commits once.
Any contribution-evidence document is a later optional asynchronous projection
with its own action and failure state, not a core transaction or joint-release
gate.

### Transactional outbox gate

The shared PostgreSQL transactional-outbox contract, ownership, and lock-order
position must be frozen before immutable review-chain persistence starts. The
preferred implementation is the merged shared foundation used by WS-CON. If it
does not exist at activation, WS-REV-001-04 is blocked until a separately
approved foundation chunk lands; WS-REV must not improvise a private competing
outbox.

### Shared audit gate

WS-REV appends to the existing shared `AuditEvent` ledger through its
caller-transaction-aware audit participant, preserving request/correlation and
AuthorizationDecision links. If bounded lifecycle event inputs are not merged,
an audit-owner foundation chunk lands before chunk 04. A `ReviewAuditEvent`
table, review-private audit repository, or commit-owning audit writer is
prohibited.

## Data model alignment

### Existing records extended

- `Submission` remains the versioned submission record and receives structured
  finding-response relationships where needed. PostgreSQL enforces immutable
  rows, same-task immediate predecessor lineage, version N-1 linkage, and the
  canonical submitter Actor mapping. It also stores the exact immutable
  TaskAssignment that produced it, constrained to the same task and contributor, so
  history and WS-CON never infer attribution from a later active assignment.
  Its submitter and assignment contributor are canonical human
  `ActorProfile.id` values. The ART submission/checker cutover supplies one
  server-derived verified `artifact_hash` on this existing versioned row; the
  XINT shorthand `SubmissionVersion.artifact_hash` does not create a duplicate
  entity, and no participant trusts caller `package_hash`.
- `WorkstreamTask` receives canonical `accepted`, `rejected`, and `cancelled`
  transitions plus bounded terminal reasons. Human reject enters `rejected`;
  the approved administrative revision-limit/deadline closure enters
  `cancelled` with its exact reason and creates no Review.
- `TaskAssignment` receives dormant completed/blocked compatibility fields.
  No service path enters either state and no reject Review reference is added
  until Review persistence and the owning decision/task participant exist.
- `ReviewPolicy` receives positive preference/lease durations, capacity fixed
  to one, self-review fixed false, close-task reject, and typed finding-evidence
  settings. Existing policy migration uses separately approved duration
  defaults and never infers either duration from `sla_hours`.
- Existing locked non-compensation task/submission policy references remain the
  immutable execution-context anchor.

### New review-owned records

- `ReviewQueueEntry`
- `ReviewLease`
- `ReviewPacketManifest`, an immutable lease/packet projection over exact queue,
  Submission version, admitting CheckerRun/results, locked guide/revision
  context, response-evidence relations, and ART binding IDs
- `Review`
- `FinalAcceptance`, an internal immutable fact created only when a new Review
  has decision `accept`; it links exactly one task, versioned Submission, source
  Review, accepted submitter, recording reviewer, acceptance time, and immutable
  ReviewPolicy context
- `ReviewFinding`
- `SubmissionFindingResponse`
- `FindingResolution`
- `ReviewEvidenceArtifact`, an immutable semantic relation from a pre-decision
  lease-scoped evidence slot to one finalized ART binding, later linked to its
  exact ReviewFinding or SubmissionFindingResponse without changing the binding
  identity
- review-owned `ReviewDecisionRequest` idempotency aggregate bound to actor,
  operation, lease, submission, and canonical payload (the existing
  AUTH-owned authority idempotency record is not reused)
- `ReviewAdministrativeCommandRequest`, a separate bounded administrative
  idempotency aggregate for repair/closure resources and payloads; it does not
  widen or overload lease/submission-bound `ReviewDecisionRequest`
- `ReviewReconciliationFinding` with immutable canonical defect/evidence facts,
  a set-once resolution pointer, and one-to-one immutable
  `ReviewReconciliationResolution` for domain inconsistency evidence
- one canonical shared outbox event for review snapshot projection; delivery
  attempts/status remain owned by the shared outbox and immutable artifact
  receipts remain owned by ART, with no review-private delivery table

All mutable-state compatibility, predecessor, uniqueness, packet-membership,
evidence-slot, and partial-active invariants are enforced in PostgreSQL as well
as in services. `ReviewLease` remains the permanent attempt identity;
`ReviewDecisionRequest` remains request idempotency. No mutable ReviewAttempt or
ReviewVersion entity is introduced.

`ReviewLease.reviewer_id`, `Review.reviewer_id`, preferred-reviewer references,
and every human administrative actor reference use canonical `ActorProfile.id`
with database-enforced human actor kind and status checks at mutation time.
Schema chunks use a composite immutable actor-kind key plus local
`actor_kind='human'` check, or an equivalently reviewed deferred constraint
trigger; a plain actor-profile FK is insufficient. Audit attribution additionally
preserves the AUTH-defined actor-reference kind so service/system work is not
misrepresented as a human reviewer.

## Application flow

```text
durable checker allow_review
  -> verify required retained binding facts
  -> create at most one open/preferred ReviewQueueEntry for an admitted version
     with task review_pending and the exact admitting CheckerRun ID
  -> server selects current lease or one next offer
  -> preliminary request-scoped authority and concealment gate permits bounded
     artifact availability preflight without disclosing packet facts
  -> final transaction: AUTH prepares and locks reviewer authority; REV locks
     the selected queue and canonical packet rows and recomposes final facts;
     AUTH evaluates once; REV and typed participants flush the ReviewLease and
     immutable ReviewPacketManifest; the request route or service command commits once
  -> authorized Review Context shows the bounded immutable chain but retrieves
     artifact content only for the currently leased Submission version
  -> finding evidence is ingested and verified before decision
  -> decision transaction locks AUTH authority first, then REV canonical rows,
     recomposes final facts, and evaluates once
  -> REV appends the immutable Review, submitted findings, and resolutions, then
     consumes the lease and closes the queue entry
  -> CON reviewer operation creates completed_review, evaluates the
     lease-frozen reviewer policy, and appends any reviewer award
  -> REV applies the decision branch
     -> accept: append FinalAcceptance, accept task, complete assignment, then
        CON submitter operation creates accepted_submission, evaluates the
        assignment-frozen submitter policy, and appends any submitter award
     -> needs_revision: set task needs_revision; no FinalAcceptance and no
        submitter operation
     -> reject: block assignment and then reject task; no FinalAcceptance and no
        submitter operation
  -> REV stages shared audit and outbox records
  -> request route or service command commits once
  -> projection and notifications execute from the canonical shared outbox
     event after commit; optional contribution-evidence export is outside the
     core readiness contract
```

### Decision invariants and outcomes

Every valid decision follows one common append-only path. After AUTH prepares
and locks reviewer authority, REV locks idempotency and the applicable lifecycle
fence, queue, ReviewLease, task, TaskAssignment, Submission, predecessor Review,
and evidence facts. REV recomposes the final context, AUTH evaluates once, and
REV appends one immutable Review plus every submitted immutable finding and
resolution. REV then consumes the ReviewLease and closes the ReviewQueueEntry.
REV next invokes the mandatory CON participant's reviewer operation, which
creates `completed_review`, evaluates the ReviewLease-frozen rule, and appends
any reviewer award. Later revision rounds append a different Review and never
update that history.

The outcome-specific effects are exact:

- `accept`: append FinalAcceptance linked to the new Review; set Task to
  `accepted`; set TaskAssignment to `completed`; invoke the same CON
  participant's submitter operation to create `accepted_submission` from
  FinalAcceptance, evaluate the assignment-frozen rule, and append any submitter
  award.
- `needs_revision`: set Task to `needs_revision`; keep the TaskAssignment active;
  append no FinalAcceptance and invoke no submitter operation.
- `reject`: block the same-task TaskAssignment, then set Task to canonical
  `rejected` with the bounded human reason; append no FinalAcceptance and invoke
  no submitter operation. No other task or project grant changes.

CON flushes contribution and award rows and returns typed audit and outbox
inputs. REV stages the shared records, and the request route or service command
commits once. Any failure
rolls back the immutable records, lifecycle state changes, contributions,
awards, audit records, and outbox records together.

## Application dependency direction

`reviews` owns review orchestration. Task-owned `TaskReviewEffectsParticipant`
and `TaskSubmissionParticipant` operations accept the caller's `AsyncSession`,
flush without commit, and reuse `TaskRepository`, the existing `Submission`,
version allocation, locked-policy checks, lifecycle guards, audit ordering, and
post-commit dispatch contract. The public task adapter owns commit and dispatch;
review code never imports `TaskRepository` or clones task rules.

Checker owns a typed review-context reader. CheckerService accepts a typed
review-admission participant implemented by reviews; the durable
`_apply_pre_review_gate_result` transaction invokes it directly and never polls
or recomputes `allow_review`. One explicit `app.composition.review_lifecycle`
constructor assembly supplies these ports to checker routers, task services,
checker execution processes, and review routers. It is not a service locator and has no
fallback constructor. Models may hold database relationships without creating
repository/service import cycles. Import-boundary tests enforce the direction.

AUTH, ART, CON, shared audit, and shared outbox are likewise injected ports.

## Joint release control

Product-surface release and shutdown use one hidden PostgreSQL-canonical
`JointLifecycleReleaseControl`, not shell-script or process-local state. Chunk
12A persists compare-and-set phase history, exposes a typed mandatory mutation
fence, and installs that fence through explicit composition across review
mutations, every task submission, review-queue admission, authority-loss
replacement, every CON-owned fulfillment-obligation root creation, requeue,
successor, and repair writer, and the exact CON-owned fulfillment dispatch and
callback hooks. Every obligation writer acquires the fence before allocating its
monotonic ordinal. It adds no public production route.

The fence uses matching PostgreSQL advisory locks so a phase transition waits
for admitted mutation transactions and then applies the persisted command-class
matrix. A dedicated `revision_cutover_fenced` phase keeps initial submission and
checker admission open while blocking legacy revision/replacement writers;
shutdown phases separately fence all new admission, drain review commands and
leases, capture the immutable fulfillment-obligation cutoff, drain only
pre-cutoff fulfillment work and completion-only callbacks, and then disable.
`disabled(N) -> pre_activation(N+1)` is the only reactivation edge and
requires a newly reviewed manifest. Every edge and observation is a fresh
Operator-authorized lifecycle command; lease draining reuses fresh
`review.lease.force_release` commands rather than widening lifecycle authority.
No background job replays human authority or advances phase. Timeout leaves phase
unchanged for forward retry and no edge attempts schema downgrade. After 12A's
hidden behavior and the other additive manifests merge,
`WS-AUTH-001-REV-LIFECYCLE` activates
`review.lifecycle.activation.manage` with the other three registered additions.
Chunk 13 then exposes the already-active Operator surface, performs the ordered
product cutover, and proves crash resume and coherent reactivation. The
controller's `pre_activation` state is a REV product-release phase, not AUTH
action availability.

## Revision flow

```text
needs_revision Review
  -> task remains assigned and enters needs_revision
  -> compare prior Submission's stamped guide identity/activation sequence with
     the project's currently active Project Guide
  -> exact match keeps; any different active identity/sequence rebases forward
     or backward; missing, incomplete, or unsafe active context blocks
  -> contributor sees prior findings and context delta
  -> same submission.create action creates next existing Submission version
  -> one SubmissionFindingResponse per unresolved blocking finding
  -> response evidence uses verified ArtifactBinding IDs
  -> existing finalization/checker spine runs
  -> allow_review creates queue entry preferred to prior reviewer
  -> preference expiry/decline/invalidation opens entry without resetting age
  -> later Review records one FindingResolution per required prior finding
```

If the current preparation becomes blocked, revoked, corrupt, or invalid after
project correction, the covered Project Manager invokes the authorized
idempotent repair command with reason and current head ID/digest. The command
locks and revalidates current authority, project context, task/assignment, prior
Submission, episode, and head, then appends exactly one successor. Concurrent
repair or submission resolves to one successor/replay or a stable stale-head
conflict. It never fabricates an episode root.

Legacy `needs_revision` rows without an originating Review/root remain readable
but cannot advance. Reconciliation reports them; an Operator-only,
evidence-linked closure releases the assignment and closes any queue with stable
terminal reason `legacy_revision_context_unrecoverable`, producing audit/outbox
evidence but no Review, contribution, award, payment, or reputation effect.

The task pipeline owns the only guide binding. TaskAssignment stores only
`task_id`; it carries no duplicate guide/context field. Each Submission stamps
its resolved context immutably. During `needs_revision`, the Task Context API resolves
the prepared next-attempt context so the submitter sees the guide context selected
from the active guide and frozen during preparation before resubmission. The
reviewer never rebases: it consumes the guide and
task-execution policy context stamped on the single Submission covered by its
active lease.
Preparation freezes exact guide/source-snapshot and task-execution policy IDs,
versions, and hashes; Task Context and Submission N+1 must use that same record.
It never freezes or rebases `ContributionPolicyVersion`. Later guide
activation does not silently drift it, while invalidation requires explicit
re-preparation.

Activation sequence records chronology but does not overrule the active guide.
When the current active guide differs, preparation records `rebased` plus
`forward` or `backward` transition direction and freezes that active guide's
complete context. A lower sequence is therefore a deliberate backward rebase,
not a manager-repair condition.

The immutable `RevisionContextPreparation` stores the complete next-attempt
context and digest. Each episode is rooted in the exact `needs_revision` Review;
manager repair appends a non-branching successor with an incremented preparation
sequence. One root per episode, one child per preparation, and same-lineage edge
constraints leave one head. Task Context selects that head before validation and
reads without mutation; an invalid or blocked head never falls back. Revision
submission acknowledges the head ID/digest. Chunk 09A replaces the current
Submission-to-task and CheckerRun-to-task context-equality FKs with direct
project/context integrity and exact Submission/preparation/checker-run bindings,
preserving original task locks and prior Submission rows.

Normal revision returns to the same assigned contributor. AUTH-13 authority-loss
reconciliation is the exceptional transfer path: it closes the old assignment
without changing history and leaves a durable unassigned obligation. A covered
manager's replacement assignment transaction invokes the review-owned
preparation-transfer participant, which appends one successor bound to the new
target TaskAssignment and the then-authoritative Project Guide context. The
episode keeps the reviewed Submission and its original assignment as immutable
source lineage; Submission N+1 and the submitter contribution-policy freeze use
the replacement target assignment. Partial transfer rolls back assignment and preparation
together.

History access and artifact-content access are separate. Authorized history may
show every Submission/Review version, findings, responses, resolutions,
guide-version transitions, and bounded audit facts. ART packet read is limited
to the immutable `ReviewPacketManifest` anchored to the active lease and its
versioned Submission:
submission, the queue's exact admitting checker-run, current finding-response evidence, and
required locked-context bindings. No prior-version packet bytes are disclosed
merely because they appear in the chain.

Historical packet projection is limited to binding ID, relation purpose/kind,
media type, verification/availability state, and required/optional class. It
contains no digest, provider locator/key/CID, signed capability, replica/receipt
detail, service scope, content excerpt, or credential.

`review.chain.read` is relationship-scoped, not project-reviewer-wide. A current
submitter may read a chain containing a Submission bound to their exact
TaskAssignment; an active reviewer may read the chain anchored to their exact
lease; a prior participating reviewer may read metadata only when they authored
a Review in that chain and still hold the exact current project `reviewer`
grant; and an
Operator/Project Manager needs the explicit inspection permission. The server
resolves these relationships from canonical rows. Arbitrary same-project,
cross-project, revoked, or caller-supplied chain IDs confer no access. Only the
active exact lease can authorize current-packet content.

Evidence intake is two phase across PostgreSQL and ART. Request-scoped preflight
derives exact scope, then ART ingests and verifies an idempotent unbound candidate
without review locks. In finalization AUTH prepares and locks human authority;
REV locks lease or prepared assignment, Submission, finding/response slot, and
packet lineage; an ART participant locks candidate/admission/binding state; REV
recomposes final facts; AUTH evaluates once; and ART binding plus
`ReviewEvidenceArtifact` relation flush together. Failure after upload can leave only an ART-owned
orphan candidate under ART retention/cleanup; it creates no Workstream binding,
review/submission relation, or lifecycle effect. Decision and submission
transactions validate the canonical binding and authority again. If merged ART
does not expose this candidate/finalize contract, chunk 07 stops for an ART-owned
foundation change rather than adding review-private storage state.

## Concurrency design

- After a preliminary request-scoped authority and concealment gate, preflight
  remote artifact availability before acquiring review row locks.
- Inside claims and decisions, use database time and targeted `FOR UPDATE` or
  atomic conditional updates over canonical rows.
- Every mutation starts with AUTH locking current actor/link/exact grant or
  service-matrix authority in AUTH-defined order and returning its opaque,
  single-use prepared handle. REV locks feature rows and recomposes final facts,
  then calls AUTH before the first feature mutation. AUTH proves exact session,
  ActionId, actor-reference kind and ID, idempotency key, canonical request digest,
  and current authority; consumes the handle exactly once; evaluates exactly
  once; and stages decision evidence. Wrong-binding, forged, serialized, and
  caller-constructed attempts do not consume the legitimate unconsumed handle;
  stale/already-consumed or concurrent duplicate attempts remain invalid and add
  no feature or evidence state. Authority loss follows the evaluated-denial path.
- Before REV-12A, hidden claim order after AUTH is review idempotency, queue,
  Task/Assignment/Submission/CheckerRun, then lease and packet-manifest rows;
  it has no public or background-command entry point. REV-12A inserts the
  lifecycle fence between idempotency and queue before product release.
- Before REV-12A, hidden evidence-finalization order after AUTH is lease or
  prepared assignment, Submission, finding/response slot, packet lineage, then
  an ART-owned database-local participant locks candidate/admission/binding
  state. REV-12A inserts the lifecycle fence before those REV rows before
  product release.
  REV never imports or directly locks ArtifactBinding/Replica repositories.
- Before REV-12A, hidden decision lock order after AUTH is decision idempotency,
  queue, lease, Task, Assignment, Submission, Review predecessor, relevant
  finding and resolution rows, and stabilized typed binding facts. REV then
  appends the immutable Review, findings, and resolutions; consumes the lease;
  and closes the queue. The CON reviewer operation owns the reviewer policy,
  contribution, and award locks and writes. REV then applies the decision
  branch. For `accept`, REV appends FinalAcceptance, applies the accepted Task and
  TaskAssignment effects, and invokes the CON submitter operation. That operation
  owns the submitter policy, contribution, and award locks and writes. REV
  appends shared audit and outbox rows after the branch. REV-12A inserts the
  lifecycle fence between idempotency and queue before REV-13 releases the
  surface.
- Revision, administrative, and service commands publish their smaller ordered
  row sets in their owning chunk and preserve the same AUTH-first prefix. Rows of
  one type lock by ascending primary key. Audit and outbox append after state
  locks. The request route or service command commits once.
- Partial unique indexes enforce one active lease per queue entry and reviewer.
- Consume stabilized typed binding facts inside the decision transaction; do
  not call a remote provider or import ART persistence while holding locks.
- Map expected constraint races to stable 409 or replay results.
- Timer jobs use deterministic batches with `SKIP LOCKED`; user claims do
  not.
- Lazy request-time recovery shares the same transition service as sweeps.
- Retry only database-classified serialization/deadlock failures, with a
  bounded attempt count. Real-Postgres tests use independent sessions and
  barriers to run both conflicting permutations and inject rollback failures
  after each cross-domain participant.
- Project-guide publication adopts the same Project-to-policy lock prefix.
  Concurrent publication versus `needs_revision` preparation must freeze one
  complete old or new context, never a mixed context, and must not deadlock.
- Checker retry/supersession and queue admission both use the
  Submission-to-CheckerRun-to-ReviewQueueEntry portion of this order, so neither
  can validate a run and then anchor a different generation.
- Decision idempotency reuses `app.core.hashing.canonical_json_hash`, shared
  request/correlation identifiers, and the proven reserve/lock/complete
  transaction shape while retaining a review-owned operation/response matrix.
  No second JSON canonicalizer or generic idempotency framework is introduced.

## API design

Use existing `/api/v1` and structured error conventions.

- Reviewer current work: active lease, one next offer, or none.
- Administrative queue inspection: complete authorized project view.
- Claim, release, decline preference, decision, context read, and chain read are
  separate capabilities.
- Override, force release, and administrative closure require dedicated
  permissions, reasons, and audit. Artifact verification recovery consumes the
  existing `artifact.verification_job.retry` action through the ART-owned
  `ArtifactOperatorRecoveryPort`; WS-REV adds no recovery permission or
  execution path.
- Request JSON never supplies authoritative project relationships, provider
  paths, CIDs, URLs, or service scopes.
- No reviewer, contributor, compensation, or lifecycle-control router is
  included in production `/api/v1` composition before chunk 13. Chunks 05-12A
  prove internal service, recovery, fence, and operational contracts while
  OpenAPI tests prove those mutations remain absent.

## Dependency ownership rule

WS-REV contracts import only merged AUTH, ART, CON, audit, and outbox ports. They
do not list dependency-module wildcards as editable scope. At chunk start, each
chunk replaces any composition locator with an exact existing file path. A
missing typed capability becomes a separately approved dependency-owner chunk;
it is not added opportunistically to a WS-REV PR.

The pre-WS-CON task/project schema may still contain retired compensation-context
locks when children 02A-02C land. Those are transitional migration inputs only.
WS-CON owns their consumer cutover and schema removal; WS-REV-09A and every
public/final context operate only after that removal and must not replace the
frozen `ContributionPolicyVersion` with a moving current policy.

## Background processing

- Preference-expiry sweep
- Lease-expiry sweep
- Reviewer-grant revocation reconciliation
- Queue/lease/review orphan reconciliation
- Review snapshot projection
- Artifact-reference reconciliation through an ART-owned typed port
- Event-driven notifications

Correctness does not depend only on scheduled delivery. Jobs reload current
PostgreSQL state and are idempotent under duplicate execution.
Protected commands use these exact proposed service rows:

| Service identity | Exact review action |
|---|---|
| `workstream.review.preference_expiry` | `review.preference_expiry.run` |
| `workstream.review.lease_expiry` | `review.lease_expiry.run` |
| `workstream.review.authority_invalidation_reconciliation` | `review.reconcile.run` |
| `workstream.review.reconciliation` | `review.reconcile.run` |
| `workstream.review.artifact_reference_reconciliation` | `review.artifact_reference.reconcile` |
| `workstream.review.projection` | `review.projection.rebuild` |

AUTH-09A's merged seven-identity ART set contains none of these identities, and
generic AUTH-09E admission creates none of them. Each requires a reviewed REV
identity-to-ActionId manifest followed by its own AUTH enum,
constraint, provisioning, static-membership, admission, and later action-
activation proof. No service row exists for the
human Operator `review.lifecycle.activation.manage` action, and shared outbox
dispatch retains its separately owned service identity.
All review jobs reuse `run_async_task`, fresh execution engine/session disposal,
stable Celery task IDs, and `sync_task_settings`. The shared outbox dispatcher
is the sole claimant/retry/dead-letter owner; reviews registers only a typed,
deterministic projection handler and records ART receipts.

## Documentation alignment

Before runtime code, adopt the reconciled active contract while preserving all
archival inputs and update precedence material. Before final proof, align
glossary, architecture lockdown, reviewer
workflow, revision replay, first-user flows, roles/permissions, templates, and
operator docs with blocking/advisory findings, server-selected offers,
contribution boundaries, controlled rebase, and deferred reputation.

## Alternatives rejected

- **Create a new SubmissionVersion table:** duplicates the existing versioned
  Submission identity and violates WS-IMP integration rules.
- **Implement temporary local role checks:** creates an authorization bypass
  that becomes difficult to remove and violates WS-AUTH precedence.
- **Let reviewers choose from the full queue:** leaks operational data and
  enables cherry-picking against the revised contract.
- **Call storage inside the decision transaction:** risks long locks and
  ambiguous cross-system atomicity.
- **Emit only ContributionRecordRequested:** conflicts with the merged
  flush-only WS-CON atomic participant contract.
- **Derive submitter contribution directly from `Review.decision`:** couples CON
  to REV decision semantics and removes the stable one-time acceptance fact.
- **Expose a FinalAcceptance create action or route:** permits acceptance facts
  outside the already-authorized review transaction and breaks one-write-path
  integrity.
- **Treat revision limits or artifact errors as reject:** fabricates human
  judgment and contaminates contributor history.
- **Build frontend concurrently:** violates backend-first sequencing before
  lifecycle guards and contracts are stable.

## Verification strategy

Every chunk runs focused tests and lint. Every runtime chunk also runs a fresh
isolated real-PostgreSQL coverage invocation; a stale `.coverage` file is never
accepted as evidence. The runner requires a disposable administrative database
URL through `WORKSTREAM_TEST_ADMIN_DATABASE_URL`, creates independent databases
for concurrent test processes, and fails rather than silently falling back. Artifact
chunks use provider-neutral fakes plus LocalStorage and MinIO conformance as
applicable. The common runtime evidence is:

```text
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
cd backend && coverage report --include='app/modules/reviews/*,app/workers/reviews.py' --precision=2 --fail-under=90
cd backend && ruff check app tests scripts
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
```

Each contract's focused test command is diagnostic evidence in addition to,
not instead of, this common runtime evidence. New/materially changed review
code remains at or above 90 percent and repository-wide coverage remains at or
above 78 percent on the same fresh run.

The final live proof covers first submit, needs revision, controlled
continuation, preferred return, preference expiry/takeover, accept with exactly
one FinalAcceptance, reject,
lease expiry, revocation during lease, evidence attachment, provider outage,
integrity failure, recovery, atomicity across FinalAcceptance and contributions,
and projection retry.
The versioned conformance matrix maps specification sections 25.1-25.9 to the
owning chunk, executable tests, live drill cases, and retained evidence.

## Delivery rule

Only one WS-REV chunk may be active. A chunk begins from current trusted main,
refreshes dependency discovery, runs required internal review, receives external
and human approval, merges, records automated memory, and stops. Cross-initiative
gates do not authorize starting the next WS-REV chunk automatically.
