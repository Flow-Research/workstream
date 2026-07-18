# Intent: WS-REV-001 Review And Revision Lifecycle

## Human goal

Implement the complete Workstream v0.1 human review and revision lifecycle from
durable checker admission through immutable review decisions, revision replay,
terminal reject, recovery, artifact-backed judgment, contribution integration,
and HTTP-visible proof.

## Why this matters

The current backend proves intake through `review_pending`, but it does not yet
provide an authorized human judgment layer. Workstream cannot certify completed
work until it can route review-ready submissions, prevent self-review and lease
hoarding, preserve every review attempt and finding, replay prior feedback on a
revision, and distinguish product judgment from checker or infrastructure
outcomes.

## Success state

- An admitted submission creates exactly one review queue entry.
- A current human holding one exact active project `reviewer` grant sees only
  their active lease or one next offered item and can claim at most one review
  globally. Separate `submitter` or `adjudicator` grants add no review authority.
- Claims, releases, preference changes, decisions, overrides, and recovery use
  current centralized authorization and canonical resource scope.
- Every human identity in task/submission/review lineage is the canonical
  active `ActorProfile.id`; service/system actors remain explicitly typed and
  cannot occupy contributor or reviewer identity.
- Reviewers see full bounded Submission/Review history, but artifact content is
  restricted to the canonical current review packet anchored to the exact
  Submission covered by their active lease.
- Every valid reviewer decision appends a new immutable `Review`. Every finding
  submitted with that Review and every later finding resolution is also
  immutable; later revision rounds append new records rather than changing old
  ones. `accept`, `needs_revision`, and `reject` remain idempotent, atomic
  decision values with their specified task and assignment effects.
- When the immutable Review decision is `accept`, the same transaction also
  creates one immutable REV-owned `FinalAcceptance` linked to that Review and
  Submission. Submitter contribution lineage consumes that stable fact rather
  than inferring acceptance from `Review.decision`.
- Revisions respond to every unresolved blocking finding, preserve both
  predecessor chains, and compare the prior Submission's stamped guide identity
  and activation sequence with the project's currently active Project Guide.
  Exact match keeps context; any different active identity or sequence rebases
  forward or backward; missing, incomplete, or unsafe active context blocks.
  Return routing prefers the prior reviewer before falling back to open FIFO.
- A supported checker-caused `needs_revision` remains a distinct CheckerRun-
  rooted remediation that keeps task context and persists a unique server-
  derived immutable source-CheckerRun relation on corrected N+1. It creates no
  synthetic Review, finding, reviewer contribution, or human actor. Controlled
  preparation/rebase, finding replay, human revision policy, and D6 closure apply
  only to an exact `Review(needs_revision)`.
- Artifact outage or integrity failure blocks judgment without creating an
  adverse contributor outcome.
- Every committed Review joins the `WS-CON-001` contribution and conditional
  compensation transaction before any public review lifecycle route is enabled.
  Every decision creates the reviewer contribution. When the decision is
  `accept`, REV also creates `FinalAcceptance`, and CON creates the submitter
  contribution from that fact.
- Guide rebase never rebases compensation: TaskAssignment freezes submitter
  terms and each ReviewLease independently freezes reviewer terms.
- Timers, revocation recovery, reconciliation, projection, audit,
  observability, and privacy-safe live drills prove normal and failure paths.

## Boundaries

- Preserve the proven project guide, task, submission, and checker spine through
  `review_pending`.
- Extend the existing versioned `Submission`; do not create a duplicate
  `SubmissionVersion` business identity.
- Maintain one Project Guide context through the task pipeline. TaskAssignment
  binds to the WorkstreamTask that owns the initial context lock rather than
  duplicating guide fields; reviewers consume the context stamped on the leased
  Submission and do not maintain a separate review guide.
- Consume `WS-AUTH-001` through its authorization kernel and decisions; do not
  query grant tables or reconstruct permissions in review code.
- Consume only typed ART-owned packet-read and evidence candidate/finalize
  capabilities backed by the canonical `ArtifactStore`; review services never
  receive the raw store, provider adapters, provider references, or scratch paths.
- Keep PostgreSQL canonical for review truth. Storage projection is derived,
  asynchronous, and retryable.
- Keep review code free of contribution-policy, award, fulfillment, and
  reputation policy. `WS-CON-001` owns the flush-only transaction participant;
  REV owns lifecycle orchestration and shared audit/outbox staging inside the
  caller transaction, while the request route or service command owns the caller
  `AsyncSession` and only commit. Core contribution/award creation performs no
  ART call or external I/O.
- Keep frontend delivery separate until backend contracts and lifecycle guards
  are stable and proven.

## Non-goals

- Self-review, reviewer bidding, multiple concurrent review leases, automated
  reviewer grants, reputation scoring, adjudication lifecycle/actions, or reject
  reassignment. The independent `adjudicator` grant exists but confers no REV
  operation in this initiative.
- Flow Node or R2 provider implementation in v0.1.
- Workstream-owned authentication, login, sessions, or credentials.
- A second artifact store or review-authoritative search index.
- Payment-provider execution, points balances, or settlement.
- A frontend implementation inside the backend-first WS-REV chunks.

## Human decisions confirmed

1. Approved provider direction: LocalStorage for development, MinIO for local/CI
   conformance, AWS S3 for production; Flow Node remains deferred.
2. ADR 0010 is retained with the clarified one-Project-Guide task pipeline,
   exact stamped guide identity/activation-sequence match keeps, any different
   currently active identity/sequence rebases forward or backward, Task Context
   visibility uses the frozen preparation, and no reviewer-side guide exists.
3. D6's recommendation is approved: limit/deadline blocks further submission while
   leaving `needs_revision` active, with only the covered Project Manager's
   explicit reason-bound `review.revision_obligation.close` command and never a
   fabricated human `reject` Review.
4. The revised reviewer `current` endpoint controls over
   the older WS-IMP full-backlog reviewer response.
5. Production enables the coherent lifecycle route set only after the
   repaired and reviewed `WS-CON-001` plan, exact lineage/digest contract,
   atomic participant, lease freeze, recovery, reconciliation, projection
   operations, and the exact merged CON-owned joint-readiness manifest exist.
6. Merged WS-XINT-001 PR #139 controls cross-initiative ownership: feature
   chunks build hidden behavior, AUTH alone registers/transfers/activates exact
   actions, and REV performs only the later joint product-surface release.
7. Project roles are independent `submitter`, `reviewer`, and `adjudicator`
   grants. REV consumes only the exact reviewer grant and reviewer invalidation.
8. Core ContributionRecord creation copies the stabilized versioned
   Submission `artifact_hash` lineage, evaluates the frozen
   `ContributionPolicyVersion`, and has no mandatory contribution-evidence
   artifact projection.
9. The v0.1 acceptance boundary is `Review(accept) -> FinalAcceptance ->
   accepted_submission`. `FinalAcceptance` is an internal REV-owned derived
   fact with no manual/public create API or separate authorization action. The
   review request uses one CON participant with an ordered reviewer contribution
   operation before the decision branch. It invokes the submitter contribution
   operation only after FinalAcceptance exists. REV stages shared audit and
   outbox records; the request route or service command commits once.
10. Merged AUTH reconciliation PR #140 is planning authority, not runtime proof.
    Exact AUTH custody, PREP, registration, service-identity, and activation gates
    apply per consumer so hidden REV work can proceed while every action remains
    unavailable; REV-13C alone releases product surfaces.
11. Guide chronology/task locking lands before hidden superseded-guide
    reactivation. Reactivation uses AUTH PREP plus a current-active If-Match
    precondition and must merge before AUTH-12 evaluator/cutover/activation.
12. Persisted release phase denies execution but does not dynamically unregister
    routers, deactivate AUTH mappings, or replace operational scheduler control.

Items 3-5 and the proposed chunk sequence were approved by the human on
2026-07-15 for planning publication. This approval does not activate a successor
implementation chunk before the planning PR merges and its separately declared
start gate is satisfied.

## Proof strategy

Use PostgreSQL constraint and concurrency tests, focused module coverage at or
above 90 percent, repository-wide coverage at or above the current 78 percent
floor, API contract tests, LocalStorage and MinIO artifact conformance, timer
and reconciliation tests, and privacy-safe HTTP-visible drills covering
revision, takeover, reject, expiry, revocation, evidence attachment, outage,
and recovery.
