# ADR 0016: Contribution Recognition Precedes External Fulfillment

## Status

Accepted for implementation through the human-approved WS-CON-001 plan and
`WS-CON-001-01` chunk. Recognition mutations remain subject to AUTH, REV,
migration, evidence and joint release gates. PILOT-10's bounded authorized
contribution evidence reads consume existing facts without activating recognition
or external fulfillment.

The [size-based rewards and dedicated Finance contract](../workstream_finance_exec.md)
amends the policy and fulfillment design below. It requires one current reward implementation within unreleased v0.1,
with superseded implementations and compatibility-only tests removed. This decision is
implementation authority, not a payment-availability claim; the
[capability ledger](roadmap_status.md) owns delivered status.

## Context

At adoption, the backend carried guide-bound payment terms. Migration
`0023_remove_task_payment_policy` now removes that obsolete storage and its
remaining runtime consumers, refusing retained facts or receipts before DDL.
This physical cleanup does not activate recognition or external fulfillment. The archival
WS-CON input proposed a broader compensation model, mandatory artifact-backed
contribution evidence, and authorization assumptions that no longer match the
merged AUTH, REV, ART, and cross-initiative contracts.

Workstream needs one repository-owned answer to four questions:

1. What proves a submitter's work was finally accepted?
2. What policy decides whether submitter or reviewer work earns an award?
3. Who owns the atomic Review-to-Contribution transaction?
4. Can storage or an external provider change recognition or eligibility?

Without one answer, review decisions could commit without required
contributions, submitter recognition could be inferred from unstable lifecycle
details, later policy edits could alter completed work, and provider behavior
could become an accidental source of award truth.

## Decision

### Recognition and acceptance

Every valid recorded human Review creates one immutable reviewer
`completed_review` ContributionRecord sourced directly from Review and
ReviewLease.

For `accept`, REV creates one immutable internal `FinalAcceptance` after the
Review. `FinalAcceptance` is the sole source for one submitter
`accepted_submission` ContributionRecord. `needs_revision` and `reject` create
no FinalAcceptance and no submitter contribution.

The accepted locked `human_review_required=false` policy uses the same shared
acceptance operation after required checks pass under exact TASK routing
authority. It creates no Review, ReviewLease or reviewer contribution. The
[current shared contract](spec_review_lifecycle.md#finalacceptance) owns source
provenance and constraints; this extends the human trigger, not the record types.

Existing `Submission` is already the version identity. FinalAcceptance stores
`submission_id`, not a new `SubmissionVersion` entity or alias. It also stores
canonical `recorded_by` and `policy_context_ref` fields owned by REV. It has no
manual API and no independent authorization action.

### Award eligibility

`ContributionPolicy` is the only target award-eligibility aggregate. Immutable
published `ContributionPolicyVersion` values contain exactly one explicit
`ContributionRule` for `accepted_submission` and one for `completed_review`.
Each rule is `unpaid` or `compensated`. Policy versions use one common
instrument, unit and adapter binding for all compensated terms. Compensated
`accepted_submission` rules have exactly three immutable alternatives: small,
medium and large. Tasks select a size, never an entered amount. Omitted size
at creation resolves to small; explicit null is invalid. A compensated
`completed_review` rule has one fixed quantity in the same instrument and unit,
or is explicitly unpaid. An unpaid rule has no definitions. Wholly unpaid
versions have null common financial fields.

Screening resolves the exact size under the guide's selected policy. Assignment
and immutable Submission copy that selected definition. New accepted work earns
exactly that one award, or zero for an unpaid rule. There is no alternate
old-model reader or writer. Incompatible data transitions fail atomically;
removing obsolete code does not authorize rewriting or deleting earned facts.

Guide activation validates and binds one policy version. Task readiness locks
it before claimability; TaskAssignment copies that lock, each Submission stamps
its attempt version, and ReviewLease copies the Submission stamp without
claim-time selection. Later publication alone never mutates active
work. After checker or human `needs_revision`, task-owned revision preparation
may atomically rebase the continuing Task and TaskAssignment to the complete
current context for the next submission attempt. Checker preparation is
implemented; genuine human Review integration remains #554 work under the same
intended policy. Preparation commits the rebase; the next immutable Submission
stamps that frozen target and consumes the revision round. Existing Submissions
and checker evidence retain their original context. A completed human Review
and reviewer award retain the prior lease version; a later ReviewLease copies
the next Submission stamp. Prior contributions and awards are never rewritten.

The owner-sized CP06/CP07/CP08 and ARCH replacements establish canonical policy
binding and locked lineage. The [completed cleanup](../backend/alembic/versions/0023_remove_task_payment_policy.py)
removes the unused guide-bound economic-policy storage and remaining response,
repository and CLI consumers through migration 0023. CON-05A/05B and CP09 are
historical groupings, not another pending removal or an activation gate. No
alias, fallback, dual read/write or implicit unpaid behavior is introduced.
The current implementation replaces superseded authoring behavior within the
same owners. Policy and submission revisions remain business evidence within
that implementation, without compatibility dispatch or old hash formats.

### Transaction ownership

REV owns Review and FinalAcceptance; the initiating command composition owns
the single commit and stages task/assignment effects through TASK participants.
Human decision and TASK post-result composition reuse the same acceptance
sequence with no private cross-owner imports or callback cycle. One mandatory
CON participant exposes two ordered
flush-only operations:

1. reviewer contribution and award evaluation before the decision branch;
2. submitter contribution and award evaluation only after the accept branch has
   created FinalAcceptance and applied accepted task effects.

There is no omnibus nullable input, no no-op production participant, and no
post-commit repair for canonical contribution creation. A CON failure rolls
back the complete review decision.
The false branch calls only the submitter operation; the same rollback covers
routing, acceptance, task effects, contributions, awards, audit and outbox.

### Authorization

AUTH exclusively owns permission/action registration, stable mapping,
ActionOwner activation custody, grants, service admission, typed contexts,
prepared mutation handles, evaluators, evidence, and availability. CON supplies
hidden product behavior and canonical facts but never registers or activates
its actions.

FinalAcceptance and derived contribution/award rows inside `review.decision`
receive no additional materialization actions. Independent reads,
administration, outbox mechanics, callbacks, and operations use exact
AUTH-owned actions and principals.
The planned `task.post_submit.route` authority similarly covers only the
guarded false/pass acceptance consequence, not a human review decision or
generic contribution write. Both triggers require their own fresh AUTH allow.

Adjudicator grants and adjudication are excluded from v0.1 and create no
dependency or capability in this lifecycle.

### Artifacts and fulfillment

The core Review-to-Contribution transaction makes no ART call. CON copies the
server-derived stabilized Submission artifact digest supplied by REV. Optional
contribution evidence is a deferred asynchronous projection requiring separate
approval and cannot gate canonical truth or release.

`CompensationAward` is the immutable evaluated result. External adapters fulfill
already-created awards through ADR 0014 typed capability ports and factories.
They cannot determine, create, change, or void eligibility. Provider I/O occurs
after a durable pre-I/O commit and outside database locks and lifecycle fences.

The selected fulfiller is a dedicated Finance module in the same backend,
database, migration chain and image. It reuses AUTH/ACTORS, AUDIT, OUTBOX and
Celery/Redis while owning payees, arrangements, conversion, plans and financial
execution. Workstream owns earned awards, fulfillment roots, receipts and
exceptions. Admission and reports traverse actual authenticated HTTP after the
sending local transaction commits; shared hosting permits no direct cross-owner
financial writes. Points conversion fulfills the original points award and
creates no additional money award.

One eligible human with the existing scoped `finance_authority` role authorizes
each initial or replacement bank-transfer attempt. New configured points credit
has no per-obligation human authorization; historical credit requires explicit
prior-fulfillment attestation. Unknown provider outcomes reconcile the same
reference and never authorize a replacement payment.

The shared outbox dispatcher owns only outbox mechanics. Every protected
handler has independent AUTH-approved authority.

### Joint release

REV owns one shared lifecycle controller and mutation fence. Every CON
fulfillment-obligation writer fences before allocating an immutable monotonic
root ordinal. During drain, only same-generation roots at or below REV's
persisted cutoff may initiate Workstream admission/delivery; no new successor
obligation is admitted. Finance's already admitted obligations retain their
independent execution eligibility across Workstream phase changes, subject to
current source/binding, Finance execution and recorded authority guards. Factual
same-reference observations and authenticated late reports remain recoverable
after Workstream disablement. Finance execution and callbacks do not become
Workstream drain dependencies.

Recognition mutation and fulfillment routes remain hidden until their behavior,
exact AUTH activation and applicable joint release proof pass. Bounded evidence
reads instead require their exact fresh read authority and response-transaction
proof; they do not enable writers or fulfillment.
The false acceptance milestone proves its exact TASK/shared-acceptance manifest
using that same controller and fence. It exposes no human review or CON
fulfillment/read endpoint and does not wait for those later surfaces. The
existing Operator lifecycle-control command receives scoped same-action
activation with real writer/observation/drain proof before admitting work;
it is shared infrastructure, not a reviewer or CON product endpoint. Shared
fence persistence/ordinal participation is pulled forward; later REV release
work extends the same mechanism rather than introducing a competing gate.

## Consequences

Positive:

- contribution recognition no longer depends on payment delivery;
- submitter acceptance has one stable REV-owned source;
- reviewer work is recognized for all three canonical decisions;
- frozen immutable policy versions prevent retroactive economic changes;
- Review and contribution cannot partially commit;
- ART and provider outages cannot erase canonical contribution or award truth;
- AUTH and feature ownership remain separated;
- one outbox and one joint lifecycle controller avoid competing mechanisms.

Tradeoffs:

- REV, CON, AUTH, task, and outbox chunks must interleave in an exact order;
- migration 0023 removes unused economic storage but refuses retained facts or
  receipts until an explicit preservation design is approved;
- protected background handlers require separate service authorities instead of
  inheriting dispatcher access;
- recognition writers stay hidden until their applicable joint gate passes;
  fresh authorized evidence reads do not wait for payment fulfillment.

## Human-Owned Gates

Before their dependent chunks begin, the human owner must approve:

- a preservation design if migration 0023 refuses retained economic facts or
  immutable receipts;
- exact D11 AdminRole candidates for standalone award administration, delivery
  recovery, and CON audit surfaces. Contribution evidence export uses the
  separately selected covering PM/exact-project Finance scope and human self
  reads; it exports complete immutable awards without asserting payment;
- exact AUTH ServiceIdentity/ActionId/static-row contracts for protected
  handlers and callbacks;
- any future optional contribution-evidence projection.

No implementation may invent defaults for these gates.

## Rejected Alternatives

- Infer submitter contribution directly from `Review.decision`: rejected
  because it couples contribution truth to REV's decision representation.
- Create FinalAcceptance manually or authorize it separately: rejected because
  it is an internal consequence of the already-authorized accept transaction.
- Use one nullable participant request for reviewer and submitter work:
  rejected because it permits crossed actor, source, and frozen-policy facts.
- Let CON own or commit the Review transaction: rejected because REV owns the
  lifecycle and must roll back all effects together.
- Keep the retired guide-bound economic policy as an alias or fallback:
  rejected because two executable eligibility models can disagree.
- Require an ART evidence artifact before contribution creation: rejected
  because storage availability must not control canonical recognition.
- Let an external adapter decide award eligibility: rejected because external
  fulfillment is not Workstream policy truth.
- Let outbox dispatch imply handler authority: rejected because generic queue
  mechanics must not become broad feature or provider authority.
- Add a second CON release controller: rejected because one shared fence and
  cutoff must govern the joint lifecycle.
- Add adjudication now: rejected because v0.1 decisions remain exactly
  `accept`, `needs_revision`, and `reject`.

## Canonical Specification

The normative implementation contract is
[`spec_contribution_compensation.md`](spec_contribution_compensation.md).
