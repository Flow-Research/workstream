# REV/AUTH <-> CON Handoff

## Boundary

REV owns Review lifecycle orchestration, FinalAcceptance, and review/task
effects. CON owns
`ContributionRecord`, `ContributionPolicyVersion` freezes, awards, delivery,
shared-outbox delivery transitions, and CON projections. AUTH owns authorization
for review and all separately exposed CON actions. The request route or service
command owns the caller `AsyncSession` transaction and its only commit. AUTH,
REV, task, CON, shared-audit, and shared-outbox participants stage or flush only.

Core ContributionRecord creation performs no synchronous ART capability call,
provider I/O, contribution-evidence artifact write, or ART authorization action.
It copies the already-stabilized `artifact_hash` on the existing immutable,
versioned `Submission` row supplied by REV into
`ContributionRecord.artifact_hash`. CON does not load or rederive that value
from ART, and no separate `SubmissionVersion` table is introduced.

## Preconditions

- reviewer and submitter use canonical human ActorProfile IDs and independent
  exact-project reviewer/submitter grants;
- TaskAssignment freezes submitter contribution policy;
- ReviewLease freezes reviewer contribution policy;
- Submission has immutable assignment/version lineage and a stabilized verified
  packet digest;
- `review.decision` registration, prepared evaluator, and grant path are ready;
- the CON participant's ordered reviewer and submitter operations and the shared
  transactional outbox are merged but hidden.

## Atomic decision transaction

```text
AUTH prepares review.decision and locks reviewer authority
-> REV locks idempotency, lifecycle fence, queue, lease, task, assignment,
   Submission, Review predecessor and stabilized binding facts
-> REV recomposes final review-decision context
-> AUTH evaluates once and stages decision evidence
-> REV appends immutable Review/findings/resolutions, consumes the ReviewLease,
   and closes the ReviewQueueEntry
-> CON reviewer operation creates one completed_review ContributionRecord,
   evaluates the ReviewLease-frozen reviewer rule, and appends any reviewer award
-> REV applies the decision branch
   -> accept: append FinalAcceptance linked to Review, accept Task, complete
      TaskAssignment, then invoke the CON submitter operation
   -> needs_revision: set Task needs_revision; no FinalAcceptance or submitter operation
   -> reject: block TaskAssignment, then reject Task; no FinalAcceptance or submitter operation
-> accept-only CON submitter operation creates accepted_submission from
   FinalAcceptance, evaluates the TaskAssignment-frozen submitter rule, and
   appends any submitter award
-> CON returns typed audit and outbox staging inputs
-> REV stages shared audit and outbox rows
-> request route or service command commits once
```

`needs_revision` and `reject` still create the reviewer contribution because a
valid Review was completed. They create neither FinalAcceptance nor a submitter
contribution. A CON failure rolls back the complete Review decision; there is no
no-op participant or post-commit repair for canonical contribution creation.

CON receives the originating AuthorizationDecision reference and canonical
locked facts through two operation-specific inputs. The reviewer input contains
no FinalAcceptance or submitter-policy lineage. The submitter input exists only
after `accept` creates FinalAcceptance and applies accepted task effects. CON
never infers submitter acceptance from `Review.decision`, evaluates that action,
reads REV or AUTH repositories, commits, or performs network/provider I/O.

## Independent CON authorization

CON requires separate AUTH actions only for its independently invoked surfaces:
contribution/award reads, contribution policy and adapter-binding management,
fulfillment callback, outbox dispatch, reconciliation, projections, and audit.
Derived contribution/award inserts inside `review.decision` do not invent
`contribution.materialize` or `compensation.award.materialize` actions.

## Optional post-commit evidence projection

A deterministic contribution-evidence document may be added later as an
asynchronous projection. It is not a gate inside the Review/ContributionRecord
transaction. If adopted, it uses a separately reviewed ART capability and AUTH
action, records projection status independently, and cannot change Review,
`ContributionRecord`, `CompensationAward`, `CompensationFulfillmentReceipt`, or
`CompensationStatusProjection` truth when storage is unavailable.

## REV owner response

REV must define the two exact participant inputs, lock order, source facts, and
request route or service command as the single transaction owner, then remove
any no-op contribution fallback.

## CON owner response

CON must keep both participant operations flush-only, remove mandatory ART
evidence from core contribution gates, preserve canonical `artifact_hash`
lineage, return typed shared-audit/outbox staging inputs to REV, and own award,
fulfillment, shared-outbox delivery, and projection transitions. Money awards
route to the payment-request/settlement adapter; project-points awards route to
the points adapter. Those adapters fulfill awards but never decide eligibility.

## AUTH owner response

AUTH must activate `review.decision` only after the complete REV+CON hidden
composition exists and independently activate each public/service CON action
after its own behavior merges.

This handoff changes no runtime and starts no downstream chunk.
