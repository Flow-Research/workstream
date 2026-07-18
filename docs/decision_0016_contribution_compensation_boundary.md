# ADR 0016: Contribution Recognition Precedes External Fulfillment

## Status

Accepted for implementation through the human-approved WS-CON-001 plan and
`WS-CON-001-01` chunk. Runtime adoption remains chunked and hidden until its
AUTH, REV, migration, evidence, and joint release gates pass.

## Context

The implemented backend still carries guide-bound payment terms. The archival
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

Existing `Submission` is already the version identity. FinalAcceptance stores
`submission_id`, not a new `SubmissionVersion` entity or alias. It also stores
canonical `recorded_by` and `policy_context_ref` fields owned by REV. It has no
manual API and no independent authorization action.

### Award eligibility

`ContributionPolicy` is the only target award-eligibility aggregate. Immutable
published `ContributionPolicyVersion` values contain exactly one explicit
`ContributionRule` for `accepted_submission` and one for `completed_review`.
Each rule is `unpaid` or `compensated`; compensated rules reference immutable
money and/or project-points `ContributionAwardDefinition` rows.

TaskAssignment freezes the submitter policy version during authorized task
claim. ReviewLease independently freezes the reviewer policy version during
authorized review claim. Later publication changes only new work.

The retired guide-bound economic-policy aggregate and all semantic and physical
consumers are removed through CON-05A/05B. No alias, fallback, dual read/write,
or implicit unpaid behavior survives.

### Transaction ownership

REV owns Review, FinalAcceptance, task and assignment effects, audit/outbox
staging, and the only commit. One mandatory CON participant exposes two ordered
flush-only operations:

1. reviewer contribution and award evaluation before the decision branch;
2. submitter contribution and award evaluation only after the accept branch has
   created FinalAcceptance and applied accepted task effects.

There is no omnibus nullable input, no no-op production participant, and no
post-commit repair for canonical contribution creation. A CON failure rolls
back the complete review decision.

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

The global independent `adjudicator` grant from ADR 0015 remains untouched but
creates no adjudication dependency or capability in this v0.1 lifecycle.

### Artifacts and fulfillment

The core Review-to-Contribution transaction makes no ART call. CON copies the
server-derived stabilized Submission artifact digest supplied by REV. Optional
contribution evidence is a deferred asynchronous projection requiring separate
approval and cannot gate canonical truth or release.

`CompensationAward` is the immutable evaluated result. External adapters fulfill
already-created awards through ADR 0014 typed capability ports and factories.
They cannot determine, create, change, or void eligibility. Provider I/O occurs
after a durable pre-I/O commit and outside database locks and lifecycle fences.

The shared outbox dispatcher owns only outbox mechanics. Every protected
handler has independent AUTH-approved authority.

### Joint release

REV owns one shared lifecycle controller and mutation fence. Every CON
fulfillment-obligation writer fences before allocating an immutable monotonic
root ordinal. During drain, only same-generation roots at or below REV's
persisted cutoff may complete; no new successor or repair obligation is
admitted.

All CON routes remain hidden until their behavior, exact AUTH activation, and
joint release proof pass.

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
- the old guide-bound economic schema requires an explicit clean-cut migration;
- protected background handlers require separate service authorities instead of
  inheriting dispatcher access;
- public surfaces stay hidden until the complete joint gate passes.

## Human-Owned Gates

Before their dependent chunks begin, the human owner must approve:

- the deterministic classification or migration of pre-production legacy
  economic rows;
- exact D11 AdminRole candidates for award detail, delivery recovery, and CON
  audit surfaces;
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
