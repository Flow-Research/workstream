# Workstream Contribution And Compensation Specification

## Status And Precedence

This is the canonical repository specification for the target Workstream
contribution and compensation boundary. It implements ADR 0016 and reconciles
the accepted WS-XINT, WS-REV, WS-AUTH, and ADR 0014 contracts.

The files under `docs/reference_specs/` are immutable archival inputs. Older
chunk specifications that describe the currently implemented guide-bound
payment fields remain useful runtime history, but they do not control the
target contribution or compensation architecture. The clean cut from those
fields is implemented only by the approved `WS-CON-001-05A` and
`WS-CON-001-05B` chunks; this specification does not claim that migration has
already occurred.

No route, model, action, service identity, or runtime behavior described here
exists merely because it appears in this document. Each behavior remains
hidden until its owning implementation chunk, AUTH activation, and joint
release gates pass.

Normative terms `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are used in their usual
requirements sense.

## Purpose

Workstream records useful human work independently from whether an external
provider later delivers money or project points.

The canonical sequence is:

```text
human Review
-> immutable ContributionRecord
-> immutable CompensationAward when the frozen rule is compensated
-> asynchronous external fulfillment
```

For accepted submitter work the sequence is:

```text
Review(accept)
-> REV-owned FinalAcceptance
-> accepted_submission ContributionRecord
-> applicable CompensationAward
```

The boundary MUST preserve four distinct facts:

1. `Review` records the reviewer's decision.
2. `FinalAcceptance` records the stable accept-only lifecycle consequence.
3. `ContributionRecord` recognizes who performed canonical work.
4. `CompensationAward` records what that work earned under a frozen policy.

Delivery, acknowledgement, receipt, and status projection are downstream
fulfillment facts. They MUST NOT create or change contribution recognition or
award eligibility.

## Scope

This specification owns the target contracts for:

- `ContributionPolicy`, immutable versions, rules, and award definitions;
- `ProjectCompensationAdapterBinding`;
- submitter and reviewer policy-version freezing capabilities;
- `ContributionRecord` and `CompensationAward`;
- the mandatory flush-only REV-to-CON decision participant;
- generic transactional outbox and shared lifecycle audit participation;
- outbound fulfillment, callbacks, immutable receipts, and rebuildable status;
- contribution, award, and bounded operations reads;
- fulfillment drain observation and joint release dependencies.

It does not own authentication, grants, permission registration, review
decisions, FinalAcceptance persistence, task transitions, artifact bytes,
provider settlement ledgers, balances, reputation scoring, or adjudication.

All public API paths use `/api/v1`. No alternate public prefix is introduced.

## Ownership Boundaries

| Boundary | Owner | Required rule |
|---|---|---|
| Authentication tokens | External Flow Identity Issuer plus AUTH verifier | Workstream verifies external tokens and does not own login, passwords, or primary sessions. |
| Authorization | AUTH | AUTH owns identifiers, mappings, grants, typed contexts, prepared handles, evaluators, evidence, activation custody, and availability. |
| Task assignment | Task subsystem | Task owns TaskAssignment creation, status, and task-claim composition. |
| Human review | REV | REV owns queues, leases, Review/finding/resolution state, FinalAcceptance, task effects, decision orchestration, and the only commit. |
| Contribution policy and recognition | CON | CON owns policy aggregates, freeze capabilities, ContributionRecord, CompensationAward, and CON reads. |
| Shared outbox mechanics | Shared outbox | The dispatcher owns claim, retry, dead-letter, replay, and finalization, but no feature authority. |
| Artifact bytes and bindings | ART | ART owns artifact persistence and capabilities; it is absent from the core Review-to-Contribution transaction. |
| External fulfillment transport | Typed compensation adapters | Adapters deliver already-created awards and never determine eligibility. |
| Joint release control | REV-12A | REV owns one shared lifecycle controller and mutation fence; CON supplies required hooks and observations. |

Domain participants MUST use the caller's `AsyncSession`, stage or flush only,
and MUST NOT commit. The request route or service command owns the transaction
and its single commit.

## Canonical Product Model

### ContributionPolicy

`ContributionPolicy` is the stable project aggregate that selects the policy
used for new work.

Canonical fields:

```text
id
project_id
name
status: draft | active | retired
current_published_version_id
created_by
created_at
retired_by
retired_at
```

At most one policy may be active for new work in a project. An active policy
MUST point to one published version. Missing policy configuration MUST fail
assignment or lease creation; it MUST NOT be interpreted as unpaid work.

### ContributionPolicyVersion

Canonical fields:

```text
id
contribution_policy_id
project_id
version_number
status: draft | published | retired
created_by
created_at
published_by
published_at
retired_by
retired_at
```

Draft content may be edited through the authorized policy service. Published
and retired content is immutable. Publishing a later version affects only new
TaskAssignments and ReviewLeases.

### ContributionRule

Canonical fields:

```text
id
contribution_policy_version_id
project_id
contribution_type: accepted_submission | completed_review
compensation_mode: unpaid | compensated
```

Every publishable policy version MUST contain exactly one rule for each
contribution type. An `unpaid` rule MUST have no award definitions. A
`compensated` rule MUST have one or two definitions: at most one `money` and at
most one `project_points` definition.

### ContributionAwardDefinition

Canonical fields:

```text
id
contribution_rule_id
contribution_policy_version_id
project_id
contribution_type
instrument_type: money | project_points
unit_code
quantity
adapter_binding_id
```

Every policy, award, and fulfilled quantity uses the same fixed-point
`NUMERIC(38, 18)` contract. API quantities are canonical decimal strings with
at most 20 integer digits and 18 fractional digits; leading plus signs, binary
floating-point, NaN, infinity, exponent notation, negative values, zero, excess
precision, and values above the database maximum are rejected rather than
rounded. Pydantic, application, and PostgreSQL validation MUST enforce
identical bounds.

For `money`, `unit_code` is an uppercase ISO 4217 code enabled for the project.
For `project_points`, it is the exact configured project-scoped unit; its
identity is `(project_id, unit_code)`, so equal text in another project is a
different unit. A definition MUST match the rule's project, policy version,
contribution type, and unit. Its binding MUST match the project and instrument.
Published definitions are immutable.

### ProjectCompensationAdapterBinding

Canonical fields:

```text
id
project_id
instrument_type: money | project_points
adapter_actor_id
route_key
status: active | suspended | retired
created_by
created_at
suspended_by
suspended_at
retired_by
retired_at
```

At most one binding is active for each project and instrument. `route_key` is a
non-secret domain routing identifier. Provider endpoints, credentials, tokens,
accounts, balances, and ledger references MUST NOT be stored in this aggregate
or exposed by product reads.

Suspension blocks new freezes and new delivery admission but preserves exact
callbacks and replay required for already-issued awards. Retirement MUST fail
while an active policy, unfinished frozen work, or an unfulfilled award still
depends on the binding.

### ContributionRecord

Canonical fields:

```text
id
project_id
task_id
submission_id
contribution_type: completed_review | accepted_submission
contributor_id
source_review_id
source_review_lease_id
source_final_acceptance_id
source_task_assignment_id
artifact_hash
contribution_policy_version_id
created_at
```

The record is immutable. It carries the exact project, task, existing
versioned `Submission`, actor, frozen policy version, and stabilized artifact
digest lineage.

Reviewer shape:

```text
contribution_type = completed_review
source_review_id = Review.id
source_review_lease_id = ReviewLease.id
source_final_acceptance_id = null
source_task_assignment_id = null
contributor_id = reviewer ActorProfile.id
```

Submitter shape:

```text
contribution_type = accepted_submission
source_review_id = null
source_review_lease_id = null
source_final_acceptance_id = FinalAcceptance.id
source_task_assignment_id = TaskAssignment.id
contributor_id = submitter ActorProfile.id
```

PostgreSQL MUST enforce mutually exclusive and complete source shapes, one
`completed_review` per Review, and one `accepted_submission` per
FinalAcceptance. Automated checker outcomes create neither contribution type.

### CompensationAward

Canonical fields:

```text
id
project_id
contribution_record_id
contributor_id
contribution_policy_version_id
award_definition_id
adapter_binding_id
instrument_type: money | project_points
unit_code
quantity
created_at
correlation_id
```

The award is immutable. It copies the instrument, unit, quantity, and binding
from the exact published definition evaluated for the contribution. At most
one award may exist per contribution and instrument. An explicitly unpaid rule
creates no award; absence of an award under that rule is a successful result.

Database constraints and application tests MUST prove the copied unit and
fixed-point quantity are byte-for-byte/decimal-equal to the definition; award
creation never recalculates, converts, rounds, or accepts binary floating point.

Fulfillment state MUST NOT be stored by mutating the award.

### CompensationFulfillmentReceipt

Canonical fields:

```text
id
compensation_award_id
project_id
adapter_binding_id
external_event_id
reported_status: fulfilled | failed
external_reference
fulfilled_quantity
fulfilled_at
failure_code
reported_at
received_at
correlation_id
```

Receipts are immutable and idempotent by their exact provider/binding event
identity. `external_event_id` is an opaque 1-128 character ASCII token matching
`[A-Za-z0-9._:-]+`, unique per adapter binding. `external_reference` is either
null or a non-secret opaque token with the same length and character bounds; it
is required for `fulfilled` and null for `failed`. Neither value is returned by
contributor/product reads or emitted in integration events.

A fulfilled receipt requires the exact award `NUMERIC(38, 18)` quantity and a
bounded fulfillment time. A failed receipt requires one closed Workstream code:
`ADAPTER_REJECTED`, `DESTINATION_UNAVAILABLE`, `PROVIDER_UNAVAILABLE`,
`PROVIDER_TIMEOUT`, or `UNKNOWN_PROVIDER_FAILURE`; unknown provider values map
to the last code before persistence. Failed receipts have null quantity,
fulfillment time, and external reference. One award has at most one fulfilled
receipt. A conflicting replay fails closed.

Raw provider secrets, authentication tokens, unbounded callback bodies,
free-form messages/codes, headers, signatures, endpoints, credentials, URLs,
markup, and provider metadata MUST NOT be persisted, logged, emitted, exported,
or returned. This prohibition does not include the bounded non-secret opaque
`external_event_id` and `external_reference` identifiers defined above; those
may be stored only in their canonical receipt/status fields and remain excluded
from product reads and integration events. Only closed canonical facts, those
bounded identifiers, and canonical request/payload digests may cross into
receipt, audit, outbox, or diagnostic records.

### CompensationStatusProjection

Canonical fields:

```text
compensation_award_id
delivery_status: pending_delivery | acknowledged_by_adapter
fulfillment_status: pending | failed | fulfilled
latest_receipt_id
external_reference
last_failure_code
delivery_timestamps
fulfillment_timestamps
updated_at
```

This projection is mutable and rebuildable from immutable awards, delivery
history, and receipts. It is not eligibility or settlement truth.

## FinalAcceptance Boundary

`FinalAcceptance` is a REV-owned immutable internal fact:

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

The existing immutable `Submission` row, together with `version` and
`supersedes_submission_id`, is the version identity. No `SubmissionVersion`
table or `submission_version_id` alias is introduced.

REV MUST create FinalAcceptance only inside an authorized `Review(accept)`
transaction and MUST enforce:

```text
UNIQUE(task_id)
UNIQUE(source_review_id)
UNIQUE(submission_id)
```

REV also owns the composite same-chain constraints across project, task,
Submission, Review, accepted submitter, reviewer, and immutable ReviewPolicy.
`policy_context_ref` points to that exact ReviewPolicy; it is not a
ContributionPolicy reference. `recorded_by` identifies the reviewer actor.

There is no public or manual create API and no independent authorization
action. `needs_revision` and `reject` create no FinalAcceptance. V0.1 has no
reopen, replacement acceptance, appeal, or adjudication path.

CON MUST create `accepted_submission` only from the supplied locked
FinalAcceptance and exact TaskAssignment. It MUST NOT infer submitter acceptance
by reading `Review.decision`.

## Policy Freezing

### Submitter freeze

During authorized task claim, the task-owned transaction locks canonical task
and assignment-eligibility facts before calling a narrow CON
participant. That participant locks the active ContributionPolicy, its current
published version, both rules, referenced definitions, and bindings. It returns
one exact version ID to be stored as:

```text
TaskAssignment.submitter_contribution_policy_version_id
```

The participant flushes only and never commits. The task subsystem owns claim
composition and status effects.

### Reviewer freeze

During authorized review claim, REV locks its queue and ReviewLease facts
before calling the corresponding CON participant. The participant performs the
same policy completeness and binding validation and returns one version ID to
be stored as:

```text
ReviewLease.reviewer_contribution_policy_version_id
```

REV owns ReviewLease schema, claim composition, and status effects. CON owns
only the freeze capability.

### Freeze invariants

- Published or retired frozen versions remain valid for already-started work.
- Later publication MUST NOT alter an existing assignment, lease,
  ContributionRecord, or CompensationAward.
- Suspension races MUST be resolved with explicit locks and both-order tests.
- Missing, draft, ambiguous, crossed-project, or incomplete policy state fails
  before the assignment or lease commits.
- Revision-context rebase MUST NOT rebase submitter award eligibility. Each new
  ReviewLease independently freezes the reviewer version then current.

## Atomic Review-To-Contribution Transaction

One mandatory `ContributionCompensationDecisionParticipant` exposes two
ordered, operation-specific methods in REV's caller-owned session. A combined
request carrying nullable FinalAcceptance or both actors' source and policy
facts is prohibited.

Canonical order:

```text
AUTH locks and revalidates exact reviewer authority
-> AUTH prepares review.decision for this session/action/actor/request
-> REV locks idempotency, release fence, queue, lease, task, assignment,
   Submission, predecessor Review, findings, and resolutions
-> REV recomposes final typed resource facts
-> AUTH consumes the handle, evaluates once, and stages decision evidence
-> REV appends immutable Review, findings, and resolutions
-> REV consumes ReviewLease and closes ReviewQueueEntry
-> CON reviewer operation creates completed_review and applicable awards
-> REV applies the decision branch
-> REV stages shared audit and outbox rows from invoked CON results
-> request route or service command commits once
```

### Reviewer operation

The reviewer operation runs for every valid `accept`, `needs_revision`, or
`reject` Review after Review creation and lease/queue closure but before the
decision branch.

Its typed input contains only locked:

- Review and ReviewLease;
- existing versioned Submission, project, and task;
- reviewer actor;
- lease-frozen reviewer ContributionPolicyVersion;
- originating allowed `review.decision` AuthorizationDecision;
- request and correlation references;
- server-derived stabilized `Submission.artifact_hash`.

It contains no FinalAcceptance, TaskAssignment contribution source, submitter,
or submitter policy. It creates exactly one `completed_review`, evaluates only
the reviewer rule, stages zero to two awards, returns typed audit/outbox inputs,
and flushes.

### Decision branches

Accept:

```text
REV appends FinalAcceptance
-> Task.status = accepted
-> TaskAssignment.status = completed
-> CON submitter operation
```

Needs revision:

```text
Task.status = needs_revision
TaskAssignment.status remains active
no FinalAcceptance
no submitter operation
```

Reject:

```text
Task.status = rejected with bounded human reason
same-task TaskAssignment.status = blocked
TaskAssignment block references the reject Review
no FinalAcceptance
no submitter operation
```

Reject MUST NOT change an actor grant, another task, or another assignment.
`closed/review_rejected` is not a canonical lifecycle token.

### Submitter operation

The submitter operation exists only after the accept branch has created
FinalAcceptance and applied accepted Task and completed TaskAssignment effects.

Its typed input contains only locked:

- FinalAcceptance and TaskAssignment;
- existing versioned Submission, project, and task;
- submitter actor;
- assignment-frozen submitter ContributionPolicyVersion;
- the originating authorization decision, request, and correlation references;
- the same stabilized artifact hash.

It contains no direct Review or ReviewLease contribution-source fields. It
creates exactly one `accepted_submission`, evaluates only the submitter rule,
stages zero to two awards, returns typed audit/outbox inputs, and flushes.

### Atomicity

CON MUST NOT commit, call ART, perform provider I/O, or provide a no-op
production participant. Any failure in either CON operation or later REV audit
or outbox staging rolls back Review, FinalAcceptance when applicable, task and
assignment effects, contributions, awards, authorization evidence, audit, and
outbox rows.

Canonical Review creation MUST NOT be enabled before this mandatory participant
and shared staging behavior are installed.

## Artifact Lineage

The core transaction makes zero ART capability calls. REV supplies the exact
server-derived stabilized `Submission.artifact_hash`; CON copies it to the
ContributionRecord without loading bytes, rehashing, verifying, binding, or
calling a provider.

The current caller-supplied `Submission.package_hash` MUST NOT be silently
treated as the stabilized digest. The owning ART/task/REV cutover must provide
the verified field and database lineage before the first canonical Review
commit.

An optional contribution-evidence document is deferred. If separately
approved, it is an asynchronous projection with independent status and failure
semantics. It requires fresh ART and AUTH contracts and MUST NOT gate Review,
ContributionRecord, CompensationAward, product reads, fulfillment, readiness,
or release.

## Authorization Contract

AUTH alone owns:

- `PermissionId` and `ActionId` catalogues and stable mappings;
- `ActionOwner` activation custody;
- human grants and fixed-service admission;
- ServiceIdentity and the static service-action matrix;
- typed principal and resource-context contracts;
- prepared mutation handles and evaluator dispatch;
- authorization decisions, evidence, invalidation, and availability.

CON owns canonical resource loading, product guards, hidden behavior, and
feature tests. Neither subsystem imports the other's repositories or mutates
the other's state.

Every protected surface follows:

```text
AUTH registers planned action, mapping, typed context, principal path,
and activation custodian
-> CON merges hidden resource composition, guards, and behavior
-> AUTH integrates the exact evaluator and alone activates the action
-> joint release exposes the surface
```

Registration, provisioning, static membership, behavior, activation, and
release are distinct. Planned actions deny in the real kernel. CON MUST NOT
construct permissions, query grants, infer roles, change availability, or
provide a production allow fallback.

### Human principals

- Task claim requires one active exact-project `submitter` grant.
- Review claim and decision require one active exact-project `reviewer` grant,
  no-self-review, and lifecycle guards.
- Self reads require exact actor ownership.
- Administrative reads and mutations require the exact action-specific
  AdminRoleGrant selected by AUTH.

No unrelated project or administrative grant substitutes. The independent
global `adjudicator` grant defined by ADR 0015 adds no action, policy, queue,
state, branch, or readiness dependency to this v0.1 boundary.

FinalAcceptance creation has no ActionId. Derived ContributionRecord and
CompensationAward inserts inside `review.decision` add no
`contribution.materialize` or `compensation.award.materialize` action.

### Prepared mutations

For mutations, AUTH first locks and revalidates current human actor/link/exact
grant rows or fixed-service actor/link rows. AUTH returns one opaque,
non-serializable, single-use `PreparedAuthorizationHandle` bound to:

- caller session;
- ActionId;
- actor-reference kind and reference;
- idempotency key;
- canonical request digest.

The owning feature then locks product rows and recomposes final typed facts.
AUTH consumes the handle, evaluates exactly once, and stages evidence. Reused,
serialized, caller-constructed, cross-session/action/actor/request,
binding-mismatched, or authority-lost handles fail before product mutation. A
failed substitution attempt does not consume an otherwise valid handle.

Reads use request-scoped authorization plus canonical pre-filtered loaders and
concealment. No authorization or grant cache survives the request.

### Fixed services

The only fixed-service admission path is:

```text
verified service token
-> active ActorIdentityLink
-> active service ActorProfile
-> immutable closed ServiceIdentity
-> exact static service-action matrix row
-> AUTH-09E typed service context
-> canonical feature resource facts
-> authorization decision
```

There is no database service grant or persisted service/action membership row.
Human grants
cannot satisfy service actions and services cannot use human grant candidates.
Missing provisioned service profile/link rows deny runtime calls and block
release readiness, but MUST NOT prevent application startup or Access
Administrator provisioning. Startup MAY fail on closed catalogue, matrix,
context, evaluator, or active-behavior parity drift.

Merged AUTH-09B provides the human-administrator-controlled
`POST /api/v1/service-actors` provisioning route and activates only
`actor.service.provision`. Provisioning creates an ActorProfile and exact
ActorIdentityLink for an already-approved closed ServiceIdentity; it creates no
role, grant, database action assignment, runtime admission, or executable
feature authority. The current closed identities and static rows cover ART
services only. Every future CON dispatcher, delivery, callback, reconciliation,
or rebuild identity therefore still requires its own human-approved feature
manifest followed by AUTH-owned identity/matrix registration, provisioning,
AUTH-09E admission, evaluator integration, and exact action activation.

### Proposed surface mappings

The following 22 mappings are product proposals, not registered or executable
identifiers. Existing PermissionIds remain stable. Policy ActionIds use the
canonical `contribution.policy.*` namespace while mapping to the existing
`compensation.policy.manage` PermissionId. AUTH must approve exact identifiers,
principals, contexts, mappings, custodians, and activation in its own chunks.

| Proposed ActionId | PermissionId | Principal / target | Protocol | Feature owner |
|---|---|---|---:|---|
| `outbox.dispatch` | proposed `outbox.dispatch` | fixed dispatcher / claimed event | T | CON-02B |
| `compensation.adapter_binding.read` | `compensation.adapter_binding.manage` | Finance / binding | Q | CON-04A |
| `compensation.adapter_binding.create` | `compensation.adapter_binding.manage` | Finance / binding collection | T | CON-04A |
| `compensation.adapter_binding.suspend` | `compensation.adapter_binding.manage` | Finance / active binding | T | CON-04A |
| `compensation.adapter_binding.resume` | `compensation.adapter_binding.manage` | Finance / suspended binding | T | CON-04A |
| `compensation.adapter_binding.retire` | `compensation.adapter_binding.manage` | Finance / dependency-free binding | T | CON-10B |
| `contribution.policy.read` | `compensation.policy.manage` | Finance / policy version | Q | CON-04B |
| `contribution.policy.create_draft` | `compensation.policy.manage` | Finance / policy collection | T | CON-04B |
| `contribution.policy.update_draft` | `compensation.policy.manage` | Finance / draft version | T | CON-04B |
| `contribution.policy.publish` | `compensation.policy.manage` | Finance / complete draft | T | CON-04B |
| `contribution.policy.retire` | `compensation.policy.manage` | Finance / published version | T | CON-04B |
| `compensation.fulfillment.report` | proposed `compensation.fulfillment.report` | exact bound service / award and binding | T | CON-08B |
| `contribution.read_self` | `contribution.read_self` | contributor / own record | Q | CON-10A |
| `contribution.read_project` | `contribution.read_project` | eligible AdminRole / project records | Q | CON-10A |
| `compensation.award.read_self` | `contribution.read_self` | beneficiary / own award | Q | CON-10A |
| `compensation.award.read_project` | `compensation.award.read` | D11 role set / project awards | Q | CON-10A |
| `compensation.delivery.reconcile` | `compensation.delivery.reconcile` | D11 role set / delivery request | T | CON-10B |
| `compensation.status.read` | `operations.status.read` | Operator / bounded status | Q | CON-10B |
| `compensation.reconcile.run` | `operations.reconcile.run` | reason-bound Operator / request | T | CON-10B |
| `contribution.projection.rebuild` | `operations.projection.rebuild` | reason-bound Operator / request | T | CON-10B |
| `audit.read` | `audit.read` | D11 role set / bounded CON audit | Q | CON-10B |
| `audit.export` | `audit.export` | D11 role set / bounded export | T | CON-10B |

`T` means the prepared mutation protocol; `Q` means request-scoped read
authorization.

These mappings do not authorize protected handler execution. Before delivery,
reconciliation, projection rebuild, or callback implementation, the human and
AUTH must approve an exact ServiceIdentity/ActionId/static-row design or an
explicitly closed dual-principal evaluator. Discovery candidate strings are
not canonical catalogue identifiers and MUST NOT be registered by CON.

`task.claim` currently has a stable PermissionId but no ActionId. CON-05A and
task-owned freeze composition must merge before AUTH registers or activates
that future action. `review.claim` and `review.decision` remain planned until
CON-06/07 and complete REV composition merge. AUTH must transfer the complete
REV action set under its canonical custody contract; CON MUST NOT define a
partial local transfer.

## Shared Transactional Outbox And Audit

The shared outbox is generic infrastructure:

- CON-02A owns persistence and append/flush in the caller transaction.
- CON-02B owns claim fencing, retry, dead-letter, replay, retention, stable
  task identifiers, explicit handler registry, and typed handler outcomes.
- CON-02C owns the shared lifecycle audit participant.

The dispatcher may claim, invoke, and finalize under `outbox.dispatch` only.
It MUST NOT inherit contribution, compensation, delivery, reconciliation,
projection, callback, ART, or provider authority from an event type. Feature
handlers validate an already-committed claim generation through a typed port,
stage feature-owned state, and return a typed outcome. They MUST NOT directly
claim or mutate OutboxEvent rows.

REV stages the audit and outbox rows for the Review decision after the reviewer
operation and the applicable branch/submitter operation. Those rows share the
same transaction and rollback boundary as the Review and contributions.

## Fulfillment

### Outbound delivery

Outbound delivery follows ADR 0014. A typed compensation capability extends
`ExternalServiceAdapter` and is constructed only through a typed
`ExternalServiceAdapterFactory[TAdapter]` with explicit composition-root
registration. Product services and handlers do not import concrete adapters,
use service locators, discover plugins, or retain fallback constructors.

Delivery uses three transaction boundaries:

1. authorize, fence, validate claim generation and award/binding facts, persist
   immutable pre-I/O intent, commit, and release database locks;
2. call the provider outside every database transaction and lifecycle fence;
3. open a new transaction to persist the bounded result and return the typed
   handler outcome.

Provider failure cannot roll back Review, ContributionRecord, or
CompensationAward. Retry and dead-letter behavior remain outbox mechanics.

### Callback

The callback requires the exact verified fixed service, profile/link,
ServiceIdentity, static action row, AUTH-09E context, active action, matching
binding route, project, award, instrument, and idempotency identity. It never
falls back to a human role or dynamic grant.

Rate limits bind the service actor and adapter binding, not a shared IP alone.
Signature/authentication failure, cross-binding or cross-project substitution,
changed replay, impossible quantity, or illegal state transition fails closed.
Exact replay is idempotent.

### Operations

Human operations surfaces create bounded durable requests and read status;
they do not execute provider calls or rebuilds inline. Independent fixed
services execute reconciliation and projection rebuild under their own exact
actions. Cross-executor use is denied. Reconciliation may add findings or
repair rebuildable projections, but MUST NOT mutate immutable Review,
FinalAcceptance, ContributionRecord, CompensationAward, or receipt truth.

## Joint Lifecycle Release And Drain

REV-12A owns the only `JointLifecycleReleaseControl` and
`JointLifecycleMutationFence`. CON MUST NOT create a second controller, phase,
generation, or availability writer.

Every creation, requeue, successor, retry-root, and repair path that can admit a
fulfillment obligation MUST:

```text
acquire the shared lifecycle mutation fence
-> validate the current generation and phase
-> allocate one immutable monotonically increasing fulfillment_obligation_ordinal
-> persist the obligation root or fail
```

CON dispatch and callback composition consume the same fence. CON also exposes
a same-session read-only `FulfillmentLifecycleDrainObservationPort` returning:

- pending, claimed, retryable, and in-flight outbox counts;
- nonterminal delivery and callback obligations;
- the current maximum immutable root ordinal.

REV captures and persists the server-derived cutoff. During
`delivery_draining`, dispatch and callback may complete only obligations from
the same generation whose root ordinal is at or below that cutoff. They MUST
NOT create a successor, retry-root, repair, or any new obligation. Post-cutoff
denial occurs before provider I/O.

Provider I/O remains outside the fence. REV imports no CON or outbox
repository; all communication is through typed ports.

## Reads And Public Release

Contribution and award reads use PostgreSQL canonical truth directly. They do
not depend on ART, optional evidence, provider availability, balances, or
settlement ledgers. Reads use stable pagination, exact self/project scope,
pre-filtering, and concealment. Provider references, credentials, and secret
routes are never returned.

All CON routes remain hidden from public OpenAPI and runtime use until:

- exact persistence, migrations, and retained tests pass;
- hidden product behavior and canonical resource loaders are merged;
- AUTH has registered and then activated every exact action and principal path;
- required service profiles and links are provisioned;
- shared outbox/audit and complete REV composition are installed;
- CON-11 publishes the exact dependency and handler manifest;
- REV consumes it through the single joint controller and completes the joint
  live drill.

Missing provisioned service rows keep readiness false but do not block startup
or administrative provisioning. Optional evidence and ART are not readiness
dependencies.

## Legacy Economic Schema Cutover

`ContributionPolicy` is the sole target award-eligibility policy. The existing
guide-bound economic-policy aggregate, its locked version fields, copied task
economic terms, and every semantic consumer are retired.

The clean cut is mandatory and split:

1. `WS-CON-001-05A` introduces assignment freezing, removes all semantic
   consumers of the legacy model, migrates or deterministically rebuilds only
   the explicitly classified pre-production data, and proves zero fallback.
2. `WS-CON-001-05B` proves zero remaining consumers and physically removes the
   dead schema with reviewed upgrade and downgrade behavior.

No alias, dual read, dual write, automatic conversion, compatibility response,
or historical executable fallback may remain. Until those chunks merge, old
runtime-oriented chunk specifications describe current implementation only and
are subordinate to this target contract.

The human-owned legacy-row classification MUST be recorded before CON-05A
starts. Ambiguous rows cause the migration to fail closed.

## Human And AUTH Gates

The following decisions intentionally remain gates rather than inferred
answers:

1. D11 must select the exact AdminRole candidates for project award detail,
   delivery recovery, and CON audit read/export before CON-10A/10B or related
   AUTH registration starts.
2. The human must classify all pre-production legacy economic rows for
   deterministic rebuild or explicit migration before CON-05A/05B.
3. The human and AUTH must approve exact fixed-service identity, action, static
   row, context, and evaluator contracts for dispatcher mechanics, outbound
   delivery, reconciliation, projection rebuild, and callback execution before
   their owning chunks.
4. Optional contribution evidence remains deferred unless separately approved
   through fresh ART, AUTH, and CON contracts.

No dependent chunk may treat an unresolved gate as an implicit default.

## Required Implementation Order

The core dependency order is:

```text
CON-01
-> CON-02A -> CON-02B -> CON-02C
-> CON-03A -> CON-03B -> CON-03C -> CON-03D
-> CON-04A -> CON-04B
-> CON-05A -> CON-05B
-> CON-06 -> CON-07
-> CON-08A -> CON-08R -> CON-08B
-> CON-10A -> CON-10B -> CON-10C
-> CON-11
```

Cross-initiative interleaving is mandatory:

```text
REV-02 exact Submission/TaskAssignment attribution
  -> CON-05A/B task freeze and legacy cutover

CON-03B ContributionPolicyVersion persistence
  -> REV-03 ReviewLease foreign key

CON-02A outbox + CON-02C audit
  -> REV-04 Review/FinalAcceptance persistence
  -> CON-03C exact contribution source schema

CON-06 reviewer freeze
  -> REV-06 claim composition

REV-09B stable lineage + CON-03C + CON-07
  -> REV-10 first canonical Review-committing transaction

CON-11 exact writer/dispatch/callback/ordinal/drain manifest + REV-12 observations
  -> REV-12A shared controller/fence
  -> AUTH action-specific activation
  -> REV-13 joint release
```

Every arrow waits for the exact runtime predecessor on then-current trusted
`main`. Planning documents are not runtime readiness evidence.

Optional CON-09A/09B evidence work is outside this order and requires a
separate explicit start after fresh review.

## Conformance And Proof

Every implementation chunk MUST bind its changed symbols and tests to the
initiative [conformance matrix](../.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/CONFORMANCE_MATRIX.md).
At minimum, final proof covers:

- immutable policy publication and both-order freeze races;
- explicit unpaid, money, project-points, and combined awards;
- one reviewer contribution for every valid Review;
- accept-only FinalAcceptance and submitter contribution;
- mutually exclusive contribution source shapes and concurrency uniqueness;
- complete rollback across AUTH evidence, Review, FinalAcceptance, task
  effects, contribution, award, audit, and outbox;
- zero ART calls in the core path;
- planned-action denial and exact human/service authority;
- dispatcher/handler and human/service separation;
- no provider I/O under database locks or lifecycle fence;
- callback replay, callback-before-ack, provider failure, and reconciliation;
- every obligation writer racing cutoff capture in both orders;
- same-generation pre-cutoff completion and post-cutoff pre-I/O denial;
- hidden-to-active route transition under AUTH and joint release control;
- no adjudication action, state, queue, lease, decision, contribution, branch,
  readiness check, or initiative dependency.

Repository-wide coverage MUST remain at or above 78 percent and every new or
materially changed subsystem at or above 90 percent. No implementation chunk
may weaken tests, CI, authorization defaults, or coverage thresholds.

## Exclusions

This specification does not add:

- login, signup, passwords, Workstream-owned primary sessions, or token roles;
- adjudication, appeal, reversal, replacement acceptance, or mutable awards;
- provider-specific SDKs before their adapter chunk;
- payment accounts, balances, payout batches, invoices, points ledgers,
  credits, blockchain settlement, or marketplace behavior;
- reputation scoring, aggregation, decay, or automatic grant decisions;
- raw ArtifactStore, storage references, provider credentials, or a second
  artifact store in CON;
- frontend work before backend contracts and lifecycle guards stabilize;
- a public route before AUTH activation and joint release proof.
