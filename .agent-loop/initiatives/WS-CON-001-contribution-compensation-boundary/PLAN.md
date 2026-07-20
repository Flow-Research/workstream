# Plan: WS-CON-001 Contribution Record And Compensation Boundary

## Proposed approach

Adopt contributor-foundation PR #153, AUTH-09D-B PR #152, ART-02B1 PR #151, planning-only REV PLAN2 PR #150, AUTH-09D-A PR #148,
merged REV-02 PR #147, REV-01 PR #145, and the underlying REV planning PR #128
plus trusted main `8d5eb15b`, including
AUTH-09C PR #146, ART PR #141, AUTH-09A, AUTH-09B PR #143, AUTH PR #140, and
the underlying WS-XINT PR #139 boundary before runtime work, then deliver WS-CON through
hidden, reviewable chunks. The
core path is PostgreSQL-local and has no ART dependency:

```text
AUTH prepares review.decision and locks reviewer authority
-> REV locks and recomposes canonical Review/Submission facts
-> AUTH evaluates once and stages decision evidence
-> REV stages Review/findings/resolutions, consumes ReviewLease, and closes queue
-> CON reviewer operation creates completed_review and applicable reviewer awards
-> on accept, REV creates immutable FinalAcceptance, accepts Task, and completes Assignment
   -> CON submitter operation creates accepted_submission and applicable submitter awards
-> on needs_revision, REV sets Task to needs_revision and keeps Assignment active
-> on reject, REV sets Task to rejected with a bounded human reason and blocks
   only the same-task Assignment with its source Review
-> REV stages shared audit and outbox rows
-> request route or service command commits once
```

Public contribution, policy, award, fulfillment, and operations surfaces stay
hidden until their exact AUTH registration -> feature behavior -> AUTH
activation sequence and the joint REV/CON release gate pass.

## Canonical product model

- `ContributionRecord` is immutable. Every valid recorded human Review creates
  one reviewer `completed_review`. REV creates `FinalAcceptance` only for
  `accept`; one submitter `accepted_submission` consumes that stable fact.
- `FinalAcceptance` is an immutable REV-owned internal derived fact, not a
  public resource command. It has no independent authorization action or manual
  creation API.
- Existing `Submission` plus its `version` and `supersedes_submission_id` is the
  versioned submission identity. WS-CON does not add `SubmissionVersion`.
- `ContributionPolicy` is the stable project aggregate. It has one active
  policy per project and points to an immutable published
  `ContributionPolicyVersion`.
- Each published version has exactly one `ContributionRule` for
  `accepted_submission` and one for `completed_review`. A rule is explicitly
  `unpaid` or `compensated`.
- An unpaid rule creates no award. A compensated rule references one or two
  immutable `ContributionAwardDefinition` rows: at most one `money` and one
  `project_points` definition.
- `CompensationAward` is the immutable evaluated result. Delivery,
  acknowledgement, immutable `CompensationFulfillmentReceipt`, and rebuildable
  `CompensationStatusProjection` are downstream fulfillment concerns and never
  decide eligibility.
- `ProjectCompensationAdapterBinding` binds one project/instrument to a
  non-secret adapter route and canonical service actor. Credentials and
  provider endpoints remain deployment configuration.
- The retired guide-bound economic schema and every semantic consumer are
  removed in two fail-closed chunks. No alias, automatic conversion, or
  executable fallback survives.

## Review and contribution boundary

One mandatory `ContributionCompensationDecisionParticipant` exposes two ordered
operation-specific methods in the caller-owned `AsyncSession`; it does not
accept one omnibus request with nullable FinalAcceptance or both actors' policy
contexts.

The reviewer operation is required for every valid decision after REV appends
Review/findings/resolutions, consumes ReviewLease, and closes the queue but
before REV applies the decision branch. Its typed input contains only exact
locked Review, ReviewLease, versioned Submission, project/task, reviewer,
lease-frozen reviewer `ContributionPolicyVersion`, originating allowed
`review.decision` AuthorizationDecision, request/correlation references, and
the stabilized server-derived `Submission.artifact_hash`. It contains no
FinalAcceptance, TaskAssignment source field, submitter, or submitter policy.

The submitter operation exists only after the `accept` branch creates
FinalAcceptance and applies Task `accepted` plus TaskAssignment `completed`. Its
typed input contains exact locked FinalAcceptance, TaskAssignment, versioned
Submission, project/task, submitter, assignment-frozen submitter
`ContributionPolicyVersion`, the same authorization/request/correlation
references, and stabilized artifact hash. It contains no direct Review or
ReviewLease contribution-source fields and is unavailable for `needs_revision`
or `reject`.

Each operation validates only its supplied locked lineage, copies the stabilized
digest into `ContributionRecord.artifact_hash`, evaluates its matching frozen
`ContributionRule`, stages applicable contribution/award rows, returns typed
audit/outbox inputs to REV, flushes, and never commits. CON never reads REV or
AUTH repositories, evaluates `review.decision`, calls ART, rehashes artifact
bytes, performs provider I/O, or offers a no-op production participant. Any CON
failure rolls back the complete Review decision.

`needs_revision` and `reject` still create the reviewer contribution and any
award earned by its frozen reviewer rule. They create no FinalAcceptance or
submitter contribution. Automated checker outcomes create neither contribution
type.

The REV-owned lifecycle effects are exact and remain inputs to CON rather than
CON behavior: `needs_revision` sets `Task.status = needs_revision` and keeps the
same TaskAssignment `active`; `reject` sets `Task.status = rejected` with the
bounded human reason and sets only the same-task TaskAssignment to `blocked`
with its reject Review reference. Reject changes no actor grant and no other
task or assignment. The archival `closed/review_rejected` wording is not a
canonical status.

### FinalAcceptance lineage

REV persists the minimal same-chain fact:

```text
FinalAcceptance
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

The external handoff's `submission_version_id` maps to `submission_id` because
the existing immutable Submission row is already the version identity. Merged
REV-04 retains `policy_context_ref` as the foreign key to the exact locked
`ReviewPolicy.id` and `recorded_by` as the reviewer ActorProfile field; CON adds
no alias. REV must prove the Review, policy, project, task, Submission,
submitter and reviewer chain. PostgreSQL enforces `UNIQUE(task_id)`,
`UNIQUE(source_review_id)`, and
`UNIQUE(submission_id)`. There is no reopen, replacement, adjudication, or
second acceptance path in v0.1.

Any reviewer-quality sampling is a non-mutating audit after the transaction. It
does not delay FinalAcceptance, create a second Review decision, or alter
acceptance/contribution truth.

Reviewer contributions require direct `source_review_id` and
`source_review_lease_id`, with `source_final_acceptance_id` null. Submitter
contributions require `source_final_acceptance_id` and
`source_task_assignment_id`, with direct `source_review_id` and
`source_review_lease_id` null. Partial unique constraints enforce one
`completed_review` per Review and one `accepted_submission` per
FinalAcceptance; checks reject mixed or missing source shapes.

## Contribution-policy freezing

TaskAssignment freezes `submitter_contribution_policy_version_id` during an
authorized task claim. ReviewLease freezes
`reviewer_contribution_policy_version_id` during an authorized review claim.
Both use a narrow CON-owned lookup/freeze participant, lock the active
`ContributionPolicy` and current published version plus referenced award
definitions and adapter bindings, return one exact version ID, flush only their
own state, and never commit.

Later policy publication changes only new assignments or leases. Retired frozen
versions remain valid for started work. Missing policy configuration is not an
implicit unpaid rule.

TaskAssignment and task-claim wiring remain task-owned. ReviewLease and review-
claim wiring remain REV-owned. CON supplies typed participants, not foreign
models, routes, lifecycle decisions, or commits.

## Authorization boundary

Trusted `main` is `8d5eb15b`, merging contributor-foundation PR #153 after
AUTH-09D-B PR #152 and ART-02B1 PR #151 and after planning-only REV
PLAN2 PR #150, AUTH-09D-A PR #148 and REV-02 PR #147,
REV-01 PR #145, AUTH-09C PR #146, ART PR #141, AUTH-09B PR #143, REV planning
PR #128, AUTH-09A, AUTH PR #140, and WS-XINT PR #139.
Runtime catalogue counts are 74 PermissionIds, 65 ActionIds, 17 active actions,
and 48 planned actions. No WS-CON or task-claim ActionId is registered. AUTH-09B
activates only the controlled human `actor.service.provision` operation;
AUTH-09C activates only administrative `actor.profile.read` and
`actor.identity_link.read`; AUTH-09D-A activates only the three actor-profile
lifecycle actions; AUTH-09D-B activates only identity-link revoke/reactivate.
None grants service execution or runtime admission. The contributor foundation
is merged: TaskAssignment and Submission now use canonical human
`contributor_id`, and contributor writes revalidate an active human profile and
identity link. It changes no ActionId, PermissionId, grant, evaluator, service
admission, or review lifecycle. AUTH-09E remains proposed. PR #140 adds reviewed AUTH
custody/PREP/activation contracts only; the custody transfers and prepared
protocol remain proposed runtime work.

WS-XINT D1/D2 is final for this plan: `ActionOwner` is the exact AUTH activation
custodian. Each protected surface follows:

```text
AUTH registers planned ActionId, stable PermissionId mapping, typed context,
principal path, and activation custodian
-> CON merges hidden canonical resource composition, guards, and behavior
-> AUTH integrates the evaluator and alone changes planned to active
-> joint release exposes the surface
```

CON never reads grants, imports AUTH repositories, constructs PermissionIds or
roles, changes availability, or supplies a production allow fallback. AUTH
never imports CON repositories or mutates contribution/award state.

PR #140's complete ART and REV custody-transfer contracts are AUTH-owned
coordination work; their runtime transfers have not yet merged. WS-CON
references the canonical AUTH `ACTIVATION_CUSTODY.md` plus WS-XINT
`AUTH_ART_HANDOFF.md` and `AUTH_REV_HANDOFF.md`; it does not prescribe a partial
transfer. CON depends on `review.claim` and `review.decision`, but AUTH must
transfer every current REV action as one complete boundary. The four proposed
additive REV actions remain unregistered until their own reviewed registration
contract.

### Human project grants

The shipping path consumes exactly two project authorities: task claim requires
one active exact-project `submitter` grant, while review claim/decision require
one active exact-project `reviewer` grant plus no-self-review and lifecycle
guards. Any unrelated project or administrative grant does not substitute.
WS-CON introduces no adjudicator grant/action, adjudication invalidation
consumer, or readiness dependency; the separate global AUTH role catalogue is
outside this lifecycle contract.

### Prepared mutation protocol

For mutations, AUTH first locks and revalidates either human actor/link/exact-
grant rows or fixed-service actor/link rows. It returns an opaque, single-use,
non-serializable `PreparedAuthorizationHandle` bound exactly to session,
ActionId, actor-reference kind/reference, idempotency key, and canonical
request digest. A fixed service additionally requires closed ServiceIdentity,
exact static service-action matrix membership, AUTH-09E admission, and active
action as code-owned validations after profile/link locks, not database lock
targets. The feature then locks canonical rows and recomposes final typed
facts; AUTH consumes the handle, evaluates once, and stages decision evidence.
AUTH and feature participants flush only; the route or service command commits
once. Substitution/reuse denial does not consume an otherwise valid handle.
Reads use request-scoped `require()` and canonical feature loaders.

Missing provisioned service ActorProfile/ActorIdentityLink rows deny that
runtime request and block release readiness, but do not fail application startup
or the Access Administrator provisioning surface. Startup may fail on closed
catalogue/matrix/context/evaluator/active-behavior parity drift.

### Fixed services and handler authority

The shared outbox dispatcher is not a catch-all feature executor.
`workstream.outbox.dispatcher` with exact `outbox.dispatch` static membership
may claim, invoke, and finalize outbox work only. It cannot inherit compensation
delivery, reconciliation, contribution projection, callback, ART, or provider
authority from an event type.

Before a protected feature handler is implemented, its owning specification and
AUTH must approve one exact ServiceIdentity/ActionId/static-row contract. The
current candidate boundaries requiring decisions are:

- outbound compensation delivery execution;
- asynchronous compensation reconciliation;
- asynchronous contribution projection rebuild;
- fulfillment result reporting by the bound external service;
- optional contribution-evidence binding, if that projection is later adopted.

Suggested semantic identifiers are discovery candidates only, not approved
catalogue strings: `workstream.compensation.delivery`,
`workstream.compensation.reconciler`,
`workstream.contribution.projection_rebuilder`, and
`workstream.compensation.fulfillment_reporter`. AUTH may instead approve a
closed dual-principal evaluator for an existing action, but CON must not infer
one. Therefore the previously proposed 22 core WS-CON ActionIds are not a final
closed runtime count until these service execution boundaries are decided.

The callback path requires a verified service token, provisioned service
ActorProfile/ActorIdentityLink, immutable approved ServiceIdentity, its exact
static matrix row, matching `ProjectCompensationAdapterBinding`, and AUTH-09E.
It never uses a human role or dynamic service grant.

## Operation-specific lock and commit order

There is no global sequence that moves CON policy rows ahead of REV lifecycle
rows. Every mutation first locks AUTH human actor/link/grant or fixed-service
actor/link authority, then its idempotency row and applicable lifecycle fence.
After that common prefix, the owning operation uses one explicit order:

- `review.decision`: REV follows its canonical idempotency/fence, queue, lease,
  task, assignment, Submission, predecessor Review, finding/resolution order;
  the reviewer operation then locks only the lease-frozen policy/rule/definition/
  binding and reviewer contribution/award rows. REV applies the branch. For
  accept, REV creates FinalAcceptance and applies accepted task/assignment
  effects before the submitter operation locks only the assignment-frozen
  policy/rule/definition/binding and submitter contribution/award rows. REV then
  stages shared audit and outbox rows;
- task/review claim freeze: the owning task/assignment/Submission or REV
  queue/lease rows first, then the selected published policy version,
  rule/definition and referenced binding, then the frozen lineage write;
- binding retirement or reconciliation that inspects task/assignment/lease
  dependencies: affected lifecycle rows in the same task/REV order first, then
  binding/policy and CON delivery/receipt/projection rows. If the bounded rows
  cannot be enumerated before locking, the operation takes its approved
  project-scoped advisory fence before either family and still locks lifecycle
  rows before policy/binding rows;
- an outbox handler: immutable claim-generation validation without handler
  ownership of outbox transitions, then its feature-owned award, binding,
  delivery, receipt, request, finding, or rebuildable projection rows.

Pure policy/binding administration that does not inspect lifecycle dependencies
locks Project and its own aggregate only. Rows of one type lock by ascending
primary key/UUID. Missing classes are skipped without reordering. Provider or
external I/O happens only after durable pre-I/O state commits and every database
transaction/fence is released.

The dispatcher owns claim, retry, dead-letter, and finalization transitions.
Feature handlers validate the committed claim generation through a typed port,
stage feature state, perform post-commit I/O under their own exact authority,
and return a typed outcome. They do not lock or mutate OutboxEvent rows.

## Optional contribution-evidence projection

A deterministic contribution-evidence document is optional later work. It is
not written or requested by CON-07, does not gate ContributionRecord creation,
and is excluded from core reads, operations, release readiness, and the joint
live drill.

If separately approved, CON-09A/09B may implement an asynchronous projection
with independent status/failure semantics through a separately reviewed ART
capability and AUTH action. Storage failure cannot change Review,
ContributionRecord, CompensationAward, fulfillment receipt, or status
projection truth. The future contract must revalidate the then-current ART and
AUTH boundaries, exact media/schema/retention/disclosure rules, and service
identity. CON never receives ArtifactStore, scratch/preparation types, provider
references, or ART repositories. PR #129's preparation foundation does not
approve this capability.

Core contribution and award reads move directly to CON-10A and read PostgreSQL
truth. They do not depend on an evidence artifact or ART read port.

## Shared outbox

CON-02A provides generic PostgreSQL persistence and caller-transaction append.
CON-02B provides the feature-neutral dispatcher, stable task IDs, claim fencing,
retry/dead-letter/replay, retention, explicit handler registry,
`OutboxClaimValidationPort`, and same-session drain observation. The outbox
subsystem owns no contribution, award, adapter, review, or provider semantics.

## Rollout

1. CON-01 adopts the merged WS-XINT contract and publishes the active
   contribution/compensation specification without altering archival inputs.
2. CON-02A/B/C land shared outbox persistence/dispatch and shared lifecycle
   audit participation, with outbox execution still disabled until its AUTH
   registration, static service identity, AUTH-09E admission, hidden behavior,
   and activation gates pass.
3. CON-03A-D add inactive policy, binding, contribution, award, delivery,
   receipt, and status persistence using the canonical names and boundaries.
   CON-03C lands only after REV's FinalAcceptance persistence target is merged.
4. CON-04A/B add hidden binding and ContributionPolicy behavior behind planned
   AUTH actions.
5. After AUTH-PREP, exact-project submitter grants, and the planned task-claim
   contract exist, CON-05A removes retired semantic consumers and lands the
   hidden participant that freezes the published ContributionPolicyVersion on
   new TaskAssignments. Task-owned claim composition consumes it before
   `WS-AUTH-001-13` enumerates/registers the task-claim ActionId, integrates its
   evaluator, and activates; 05B then drops unreachable physical schema after
   zero-consumer proof.
6. CON-06 supplies reviewer policy freeze; the REV owner wires it into hidden
   review claim behavior before AUTH activates `review.claim`.
7. CON-07 supplies the flush-only decision participant that consumes REV-owned
   FinalAcceptance for submitter work; the REV owner wires it into the complete
   hidden decision path and owns audit/outbox staging before AUTH activates
   `review.decision`.
8. CON-08A/R/B add fulfillment delivery and callback behavior only after exact
   service execution/callback identities, actions, static rows, AUTH-09E, and
   lifecycle fencing are approved. Every fulfillment-obligation root writer,
   requeue, successor, and repair path acquires the shared lifecycle fence
   before allocating its immutable monotonic ordinal. Dispatch and callback
   composition exposes same-generation/pre-cutoff completion behavior without
   provider I/O under the fence.
9. CON-10A/B add PostgreSQL product reads and bounded operation requests; 10C
   adds independently authorized reconciliation/rebuild executors. Optional
   09A/09B remain outside the core dependency sequence.
10. CON-11 proves hidden readiness. It enumerates every obligation writer and
    supplies mandatory dispatch/callback hooks plus a same-session observation
    port returning outbox/fulfillment counts and the maximum root ordinal. REV-
    12A injects the one shared `JointLifecycleMutationFence`, persists the
    generation cutoff, and owns release-control state; CON creates no second
    controller. REV-13C owns final public release and the joint live drill.

Every chunk refreshes trusted-main SHA, migration custody, exact port/action
symbols, and merged dependency evidence. No cross-initiative successor starts
automatically.

`REV-12A` and `REV-13` are canonical non-executable parent split records. Their
concrete runtime children control this plan: REV-12A1 persists the sole joint
controller, REV-12A3 composes the CON writer/dispatcher/callback/cutoff/drain
fences, and REV-13C alone releases the public product surface.

### Merged REV interleaving

Merged REV PR #128 fixes cross-initiative gates without starting either
initiative automatically:

```text
REV-02 immutable Submission/TaskAssignment attribution
  -> CON-05A/B task freeze and retired-field cutover

CON-03B ContributionPolicyVersion persistence
  -> REV-03A ReviewLease foreign key

CON-02A shared outbox + CON-02C lifecycle audit participant
  -> REV-04B Review/FinalAcceptance persistence
  -> CON-03C exact contribution source schema

CON-06 reviewer policy freeze
  -> REV-06A claim composition

REV-09B stable lineage + CON-03C schema + CON-07 two-operation participant
  -> REV-10 first canonical Review-committing transaction

CON-02B dispatcher/handler registry -> REV-12P1 projection handler

CON-11 writer/dispatch/callback/ordinal/drain manifest + REV-12P3 observations
  -> REV-12A1 controller persistence -> REV-12A3 CON fence composition
  -> AUTH action-specific activation
  -> REV-13C joint release
```

The merged REV plan proves ownership and ordering only. Each arrow still waits
for the exact runtime predecessor on then-current trusted main.

## Verification strategy

- Isolated PostgreSQL migration, constraint, rollback, idempotency, and both-
  order concurrency tests.
- Bounded local focused coverage for each new/materially changed subsystem at
  or above 90 percent; after PR push, GitHub CI runs the repository-wide suite
  and enforces repository coverage at or above 78 percent.
- Exact contribution cardinality for all three decisions and repeated/revision
  Reviews; accept-only FinalAcceptance one-to-one constraints; mutually
  exclusive reviewer/submitter source shapes; automated checks create none.
- Policy publication/freeze races, explicit unpaid rules, immutable published
  versions, and at most one award per contribution/instrument.
- Participant fault injection proving Review/FinalAcceptance/task/contribution/
  award/audit/outbox atomic rollback and no ART call.
- AUTH tests for planned denial, exact grant/static-matrix candidates, prepared
  handle misuse, role-specific revocation, cross-service denial, and one
  activation custodian per action.
- Outbox tests proving the dispatcher cannot execute feature authority and each
  protected handler has an approved independent authorization path.
- Callback/delivery/reconciliation tests with no provider I/O under database
  locks and immutable receipt/award identities under replay.
- Hidden OpenAPI proof before release; exact `/api/v1` inventory at release.
- Stale wording, stale authorization/artifact contracts, Markdown links, loop
  memory, `git diff --check`, and one-sheet roadmap checks when local sheets are
  present.

## Open human/AUTH decisions

- D11 exact AdminRole candidate sets for award detail, delivery recovery, and
  WS-CON audit actions.
- Exact ServiceIdentity/ActionId/static-row design for each protected feature
  handler and fulfillment callback; proposed strings are not executable until
  approved and registered by AUTH.
- Legacy pre-production row classification before CON-05A/05B migration.
- Optional evidence projection remains deferred unless separately approved.
- No adjudication decision remains: v0.1 accept/reject are terminal and no
  adjudication initiative or readiness gate may enter the core order.

## Review and stop

Planning and every specification/runtime chunk require senior engineering,
QA/test, security/auth, product/ops, architecture, docs, and reuse/dedup.
Runtime/test chunks add test-delta; background-execution/script/config/CI changes add CI
integrity. Stop after planning reconciliation. Do not start CON-01 or another
initiative without explicit human instruction.
