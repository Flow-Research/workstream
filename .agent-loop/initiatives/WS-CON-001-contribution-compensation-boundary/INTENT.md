# Intent: WS-CON-001 Contribution And Compensation

> Historical PLAN4 planning baseline. Live 03A implementation state is in
> `STATUS.md`, `SOURCE_MANIFEST.md`, and the `WS-CON-001-03A` contract.

## Goal

Complete the backend contribution and conditional-compensation boundary on
current `main` without taking ownership of review judgment, authorization,
artifact custody, external settlement, or reputation scoring.

Workstream must turn authorized human review into immutable facts:

- every committed human Review creates one reviewer `completed_review`
  ContributionRecord;
- only an accepted Review creates REV-owned `FinalAcceptance`, which is the
  source of one submitter `accepted_submission` ContributionRecord;
- locked ContributionPolicy rules decide whether either contribution creates
  no award or immutable money/project-points CompensationAwards;
- fulfillment happens asynchronously and never controls lifecycle truth.

## Current-main reason for PLAN4

The original plan stopped at the July 2026 outbox-persistence milestone. Since
then AUTH, ART, REV/XINT, project-policy, CI, and repository contribution rules
changed materially. The authored CON status still described CON-02A as active,
AUTH-09E/PREP as future, and an obsolete migration head. PLAN4 replaces those
operational claims with a capability-ordered plan, now refreshed through
`main` `2feaf47d`.

## Success state

- ContributionPolicyVersion is the only award-policy authority.
- Publication never silently changes an active attempt. Human
  `needs_revision` is the only in-progress boundary that atomically rebases
  every changed applicable next-attempt context component, including the
  submitter ContributionPolicyVersion; completed history remains immutable.
- Guide activation binds one policy version; task readiness locks it before the
  task becomes claimable.
- TaskAssignment and REV-owned ReviewLease inherit that same task-governing
  version; neither claim path selects policy.
- ContributionRecord and CompensationAward rows are immutable and replay-safe.
- REV owns Review, FinalAcceptance, task/assignment effects, audit/outbox
  staging, and the single transaction commit.
- CON exposes narrow caller-session participants and never commits REV work.
- ART supplies stable accepted Submission/binding identity; CON performs no
  provider read or write in the decision transaction.
- AUTH owns every PermissionId, ActionId, ServiceIdentity, matrix row,
  evaluator, prepared-authority capability, and action activation.
- Delivery, callbacks, reconciliation, and projection executors each use their
  own authority; dispatcher authority never transfers to a handler.
- Optional contribution-evidence projection remains separate from core
  PostgreSQL contribution and award truth.

## Non-goals

- Workstream login, password, session, or token issuance.
- Review queue, lease, judgment, finding, revision, or FinalAcceptance
  ownership.
- Artifact bytes, provider credentials, scratch paths, or storage decisions.
- Payment accounts, balances, payout ledgers, KYC, blockchain settlement, or
  provider SDK integration.
- Reputation scoring or runtime reputation projection.
- Adjudication, appeals, reversals, or mutable contribution history in v0.1.
- Frontend work before the backend contracts and lifecycle guards are stable.

## Human decisions retained

- Review decisions remain exactly `accept`, `needs_revision`, and `reject`.
- Reviewer contribution exists for all three valid decisions.
- Submitter contribution exists only through FinalAcceptance on accept.
- Explicit unpaid rules create no CompensationAward.
- Optional evidence projection is not a release prerequisite.
- Each implementation chunk remains separately bounded and stops at its own
  human merge checkpoint.
