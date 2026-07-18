# Intent: WS-CON-001 Contribution Record And Compensation Boundary

## Human-level goal

Implement the canonical contribution-policy, ContributionRecord,
CompensationAward, fulfillment, and operations boundary that participates
atomically in human Review without taking ownership of authentication,
authorization, review decisions, artifact storage, external settlement, a
points ledger, or reputation scoring.

The supplied WS-CON reference pair is input to reconcile, not authority to
accept blindly. The active contract follows trusted repository decisions and
current main `053242b`, including merged AUTH-09B PR #143, REV PR #128, AUTH PR
#140, and the underlying WS-XINT-001 boundary from PR #139.

## Success state

- Every valid recorded human Review creates one immutable reviewer
  `completed_review` contribution.
- REV creates one immutable `FinalAcceptance` only for `Review(accept)`.
  `accepted_submission` consumes that FinalAcceptance; it is never inferred
  directly from `Review.decision`. `needs_revision` and `reject` create neither.
- TaskAssignment and ReviewLease freeze independent published
  ContributionPolicyVersions before work is performed.
- Explicit unpaid rules create no award; compensated rules create at most one
  money and one project-points CompensationAward.
- REV owns the request and single commit: Review/task effects, optional
  FinalAcceptance, CON-flushed contributions/awards, and REV-staged shared
  audit/outbox rows commit or roll back together.
- One mandatory CON participant exposes a reviewer operation before the
  decision branch and an accept-only submitter operation after FinalAcceptance
  and accepted task effects; no nullable cross-actor omnibus input exists.
- Core contribution creation copies stabilized artifact-hash lineage supplied
  by REV and has no ART or provider dependency.
- Downstream adapters fulfill awards but never determine eligibility.
- Every fulfillment-obligation writer uses REV-12A's one shared lifecycle fence
  before monotonic root-ordinal allocation; drain dispatch/callback completes
  only same-generation roots at or below the persisted cutoff.
- Every protected human/service surface uses AUTH's exact grant or
  ServiceIdentity/static-matrix path, prepared mutation protocol when needed,
  and AUTH-owned activation.
- Public APIs use `/api/v1` only.

## Non-goals

- Workstream-owned login, sessions, passwords, or token-role authority.
- AUTH catalogue, grant, static-matrix, evaluator, or activation implementation.
- REV models, routes, lifecycle decisions, or commits.
- Mandatory contribution-evidence artifacts. A future projection is optional
  and separately approved.
- Provider-specific settlement SDKs, attempts, payout batches, accounts,
  balances, points ledgers, credits, or blockchain work.
- Reputation scores, aggregates, adjudication, appeals, reversals, or mutable
  contribution/award truth. V0.1 has no adjudication policy, action, queue,
  lease, state, decision, contribution, branch, readiness gate, or initiative
  dependency.
- A second artifact store, raw provider references, or ArtifactStore injection.
- Frontend work before backend contracts and guards stabilize.

## Context

Workstream certifies useful human work independently from external fulfillment.
Reviewer work is a contribution for every valid Review. ContributionPolicy
decides what that work earns. FinalAcceptance is the stable REV-owned fact that
allows CON to recognize accepted submitter work without treating the mutable
shape of a Review decision as its source. Immutable awards record the result;
adapters carry out fulfillment later.

## Human judgment required

1. Approve the repository-owned active specification while preserving archival
   reference inputs.
2. The complete removal of the retired guide-bound economic schema remains
   approved; choose only the deterministic pre-production row classification
   for migration.
3. Resolve D11 action-specific AdminRole candidates for award detail, delivery
   recovery, and audit.
4. Approve exact ServiceIdentity/ActionId/static-row boundaries for dispatcher,
   delivery, reconciliation, projection rebuild, and callback execution. The
   shared dispatcher cannot inherit handler authority.
5. Optional contribution-evidence projection remains deferred unless separately
   approved.

## Risk class

L0 for planning/contract reconciliation. Each runtime chunk is L1 because it
touches authorization, economic records, schema, lifecycle, audit, or cross-
domain transactions.
