# Joint REV/CON Release Handoff

## Boundary

REV owns Review decisions, FinalAcceptance, queue/lease/task effects, shared
audit/outbox staging for the decision transaction, release-control state, and
the single route commit. CON owns ContributionPolicy, ContributionRecord,
CompensationAward, fulfillment behavior, and CON projections. AUTH owns all
authorization and activation.

The canonical cross-boundary source is merged
`WS-XINT-001/REV_CON_HANDOFF.md`. Merged REV PR #128, originally landed at
`0302bcf` and retained in current main `053242b`, is the reviewed owner contract;
runtime REV behavior remains unimplemented.

## Required decision composition

```text
AUTH locks exact reviewer authority and prepares review.decision handle bound to
session/action/actor reference/idempotency key/canonical request digest
-> REV locks and recomposes canonical facts
-> AUTH consumes the handle, evaluates once, and stages decision evidence
-> REV stages Review/findings/resolutions, consumes ReviewLease, closes queue
-> CON reviewer operation creates completed_review from Review/ReviewLease,
   evaluates only the lease-frozen reviewer rule, and returns typed staging inputs
-> on accept, REV creates immutable FinalAcceptance linked to Review,
   canonical Submission, Task, submitter, reviewer and locked ReviewPolicy
   then accepts Task and completes TaskAssignment
   -> CON submitter operation creates accepted_submission from FinalAcceptance
      and TaskAssignment, evaluates only the assignment-frozen submitter rule,
      and returns typed staging inputs
-> on needs_revision, REV sets Task to needs_revision and keeps TaskAssignment active
-> on reject, REV sets Task to rejected with a bounded human reason and blocks
   only the same-task TaskAssignment with its source Review
-> REV stages shared audit/outbox rows from the typed participant result
-> request route or service command commits once
```

The participant is one mandatory interface with two ordered operation-specific
inputs. The reviewer input never carries nullable FinalAcceptance or submitter
policy/source facts. The submitter input does not exist outside `accept` and
never uses direct Review/ReviewLease contribution-source fields.

No no-op participant, post-commit repair, ART call, evidence projection, or
provider I/O exists in this transaction. CON copies stabilized artifact-hash
lineage from REV facts.

## FinalAcceptance contract

The external shorthand `submission_version_id` means canonical
`Submission.id`; the repository stores `submission_id` because each immutable
Submission row is already one version. Merged REV-04 retains
`policy_context_ref` as the foreign key to the exact locked `ReviewPolicy.id`
and retains `recorded_by` for the canonical reviewer ActorProfile. CON consumes
those owner-defined names without aliases. REV owns this record and the
composite same-chain constraints.

```text
FinalAcceptance
  id
  project_id
  task_id                  UNIQUE
  submission_id            UNIQUE
  source_review_id         UNIQUE
  accepted_submitter_id
  accepted_at
  recorded_by
  policy_context_ref
```

It is created only inside `Review(accept)`. There is no public/manual creation
API and no separate authorization action. `needs_revision` and `reject` create
none. Accept/reject are terminal in v0.1; there is no adjudication, appeal,
replacement acceptance, or reopen path.

For `needs_revision`, REV keeps the same TaskAssignment `active`. For `reject`,
REV blocks only that same-task TaskAssignment, binds the block to the reject
Review, and sets the Task to canonical `rejected` with its bounded human reason;
it changes no grant or unrelated task. The archival `closed/review_rejected`
wording is not a lifecycle token.

Optional reviewer-quality sampling is non-mutating audit only. It does not
delay or replace FinalAcceptance and cannot change Review/task/contribution
truth.

`completed_review` binds directly to Review and ReviewLease and is unique per
Review. `accepted_submission` binds to FinalAcceptance and TaskAssignment and
is unique per FinalAcceptance. Database checks make those source shapes
mutually exclusive; CON never infers a submitter record by reading
Review.decision.

## Release prerequisites

- ContributionPolicy publish/freeze and adapter-binding behavior are merged.
- TaskAssignment and ReviewLease carry exact frozen policy-version IDs.
- REV FinalAcceptance persistence and its locked decision-lineage contract are
  merged, including exact task/Review/Submission uniqueness and ReviewPolicy
  lineage.
- Shared outbox/audit participants and CON-07 are mandatory and merged.
- REV hidden claim/decision composition then consumes CON-06/07 and has no
  fallback.
- AUTH complete REV custody transfer, exact evaluators, reviewer grant path,
  prepared protocol, and activation are merged. The transfer is the complete
  PR #140 19-action map, not a local review.claim/review.decision subset.
- Every public/service CON action has exact AUTH registration, evaluator,
  principal path, and activation after hidden behavior.
- Protected outbox handlers have their own exact service authority; dispatcher
  authority is not inherited.
- Every CON fulfillment-obligation creation, requeue, successor, and repair
  writer exposes a mandatory hook that acquires REV-12A's shared
  `JointLifecycleMutationFence` before allocating an immutable monotonically
  increasing root ordinal or locking obligation rows.
- CON dispatch and callback hooks consume that shared fence. In
  `delivery_draining`, they may complete only the same generation and a root
  ordinal at or below REV's persisted cutoff; they cannot create successor,
  retry-root, repair, or other follow-on obligations.
- `FulfillmentLifecycleDrainObservationPort` is same-session/read-only and
  returns pending/claimed/retryable/in-flight counts, nonterminal delivery and
  callback obligations, and the current maximum root ordinal through typed
  shared-outbox capability. REV imports no CON/outbox repository.
- Exact migrations, handler registry, task IDs, route inventory, and retained
  tests are bound to merged SHAs.

ART storage and optional contribution-evidence projection are not prerequisites.

## Startup and readiness

Startup fails on closed catalogue/static-matrix/context/evaluator/active-feature
parity drift. Missing provisioned fixed-service ActorProfile/link rows do not
stop startup or administrative provisioning, but runtime calls deny and release
readiness remains false until exact rows exist.

## Joint live proof

The release drill covers accept with exactly one FinalAcceptance, accepted Task,
completed Assignment, and submitter contribution; needs_revision with an active
Assignment and neither acceptance fact nor submitter contribution; reject with
canonical rejected Task, same-task blocked Assignment/source Review, and neither
acceptance fact nor submitter contribution; one reviewer contribution per
Review, explicit unpaid, money+points, frozen-version changes,
repeated/revision Reviews, no-self-review, grant revocation, source-shape and
uniqueness conflicts, atomic rollback, adapter outage/replay,
callback-before-ack, failure then fulfillment, reconciliation, every obligation
writer versus cutoff capture in both orders, same-generation pre-cutoff
dispatch/callback completion, post-cutoff denial before provider I/O, drain
fencing, and hidden-to-active route transition. It asserts zero ART calls and
no adjudication action/state/queue/readiness dependency.

## Ownership and stop

CON-11 publishes the hidden dependency manifest but registers no route. The
reviewed REV release chunk consumes that manifest and owns public activation and
the joint live drill. This handoff starts neither chunk automatically.
