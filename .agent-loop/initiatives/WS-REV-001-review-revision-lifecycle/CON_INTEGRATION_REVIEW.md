# WS-CON Integration Review For WS-REV-001

## Authority And State

Reconciled on 2026-07-17 against merged AUTH reconciliation PR #140 at trusted
main `299363af5d9e8a68bcc9b17457188048483caeed`, merged WS-XINT-001 PR #139, and
the amended `REV_CON_HANDOFF.md`. The handoff now incorporates the explicit human
amendment establishing FinalAcceptance, two ordered CON operations, REV-owned
audit/outbox staging, and request-route/service-command commit ownership. Sibling
WS-CON worktree content remains discovery evidence until its owning contracts
merge; it cannot act as a runtime dependency.

## Ownership Boundary

REV owns queue, ReviewLease, ReviewPacketManifest, ReviewEvidenceArtifact,
Review/finding/revision state, FinalAcceptance, decision orchestration, task
effects, shared audit and outbox staging, and joint product-surface release. The
request route or service command owns the caller transaction and its only commit.
CON owns ContributionPolicy,
immutable ContributionPolicyVersion and rules, ContributionRecord, awards,
fulfillment, CON audit/projections, and every
separately exposed CON surface. AUTH owns review authorization and action
activation. ART owns bytes, bindings, verification, recovery, and typed artifact
capabilities.

REV-12A owns one shared hidden `JointLifecycleReleaseControl` and typed mutation
fence. CON supplies mandatory fulfillment obligation-writer, dispatch, and
callback fence hooks plus one same-session drain-cutoff and observation port.
CON allocates an immutable,
monotonically increasing ordinal for each fulfillment-obligation root only after
the shared fence is acquired. REV persists only the server-derived cutoff and
never imports CON or outbox repositories. The shared dispatcher owns
claim/retry/dead-letter state. A CON handler receives an already-claimed command
and may stage a delivery attempt under the normal active-phase rules. During
`delivery_draining`, that root must be in the eligible pre-cutoff cohort. The
handler never claims or transitions the outbox event itself.

## Atomic Decision Contract

```text
AUTH prepares review.decision and locks reviewer authority
-> REV locks idempotency, queue, lease, task, assignment,
   versioned Submission, Review predecessor, findings and stabilized facts
-> REV recomposes final typed review-decision context
-> AUTH evaluates once and stages decision evidence
-> REV appends immutable Review, findings, and resolutions; consumes the lease;
   and closes the queue entry
-> CON reviewer operation creates completed_review
-> CON evaluates the ReviewLease-frozen reviewer rule and appends any award
-> REV applies the decision branch
   -> accept: append FinalAcceptance, accept task, complete assignment, then
      CON submitter operation creates accepted_submission from FinalAcceptance and
      evaluates the TaskAssignment-frozen submitter rule
   -> needs_revision: set task needs_revision; no FinalAcceptance and no
      submitter operation
   -> reject: block assignment, then reject task; no FinalAcceptance and no
      submitter operation
-> explicit unpaid creates no award; payable creates immutable money and/or
   project_points CompensationAward rows
-> CON flushes contribution and award rows and returns typed audit and outbox inputs
-> REV stages shared audit and outbox rows
-> request route or service command commits once
```

This is the hidden pre-12A order and has no public or background-command entry
point. REV-12A inserts the mandatory lifecycle fence between idempotency and
queue before REV-13 releases the decision surface; the remaining order and CON
participant contract do not change.

One mandatory typed CON participant exposes the two ordered operations above in
the caller's AsyncSession. The reviewer operation receives the originating
AuthorizationDecision and locked Review and ReviewLease facts. The submitter
operation additionally receives FinalAcceptance and TaskAssignment facts and is
unavailable for `needs_revision` or `reject`. CON never infers submitter
acceptance from `Review.decision`, performs a separate authorization check for a
derived record, imports REV or AUTH persistence, commits, or performs network or
provider I/O. A failure in either CON operation or any later REV stage rolls back
the complete review decision. There is no no-op participant or post-commit
repair for canonical contribution creation.

No canonical Review-committing service may land before the CON participant.
REV-08 therefore freezes schemas, pure validation, task-effect inputs, and the
participant request only. After stable REV-09B lineage exists, CON may implement
the participant; REV-10 creates the first hidden canonical decision transaction.

## Exact Lineage Contract

The repository's existing `Submission` row is the version identity; no separate
SubmissionVersion table is added. FinalAcceptance is a REV-owned immutable
internal fact with:

- canonical `submission_id`, implementing the handoff's conceptual
  `submission_version_id`;
- exact project, task, source Review, acceptance time, and canonical human actor
  lineage: `accepted_submitter_id` equals the contributor on the reviewed
  Submission and TaskAssignment, while `recorded_by` equals the reviewer on the
  source Review and ReviewLease;
- `policy_context_ref` constrained to the immutable ReviewPolicy row matching
  the reviewed Submission context; and
- unique task, source Review, and Submission constraints.

There is no public/manual FinalAcceptance creation API or independent AUTH
action. Only the already-authorized accept decision creates it.

Both contribution shapes receive common project/task/Submission/digest lineage,
but their canonical sources are distinct:

- reviewer `completed_review` receives `Review.id` and `ReviewLease.id` directly,
  with FinalAcceptance and TaskAssignment source fields null;
- submitter `accepted_submission` receives `FinalAcceptance.id` and the exact
  `TaskAssignment.id`, with direct Review and ReviewLease source fields null;
- each receives canonical actor IDs and its exact frozen
  `ContributionPolicyVersion`;
- each receives the server-derived stabilized `Submission.artifact_hash`, copied
  to `ContributionRecord.artifact_hash`; and
- each retains originating AuthorizationDecision, request, and correlation
  references.

The XINT `SubmissionVersion.artifact_hash` wording means the field on the
existing versioned Submission row. It does not authorize a duplicate entity.
Current caller-supplied `Submission.package_hash` is not silently renamed or
trusted; the ART submission/checker cutover must add the exact verified field and
database binding before REV-10. CON does not call ART to load or rederive it.

PostgreSQL enforces one `completed_review` per Review and one
`accepted_submission` per FinalAcceptance, plus mutually exclusive reviewer and
submitter source shapes.

## Independent CON Authorization

Derived ContributionRecord and CompensationAward inserts inside
`review.decision` do not create `contribution.materialize` or
`compensation.award.materialize` actions. CON requires its own AUTH actions only
for independently invoked reads, policy/binding administration, callbacks,
outbox dispatch, reconciliation, projections, and audit. REV-13 does not edit or
register CON routers; it consumes the exact merged CON readiness manifest and
verifies that CON-owned surfaces are already composed by their owner.

## Optional Evidence Projection

A deterministic contribution-evidence document may be added later as an
asynchronous projection with its own ART capability, AUTH action, status, and
failure lifecycle. It is not created or required by the core Review transaction,
does not gate CON readiness or REV product release, and cannot change Review,
ContributionRecord, CompensationAward, fulfillment receipt, or status truth when
storage is unavailable.

## Required Interleaving

```text
REV-02 exact Submission/TaskAssignment lineage
  -> CON contribution-policy and legacy-policy cutover

CON ContributionPolicyVersion persistence
  -> REV-03 ReviewLease FK

CON shared outbox + lifecycle-audit participants
  -> REV-04 immutable Review and FinalAcceptance persistence

CON ReviewLease freeze capability + AUTH prepared mutation protocol
  -> REV-06 claim integration

REV-04 stable FinalAcceptance schema
  -> CON exact FinalAcceptance-sourced contribution schema

REV-09B stable review/revision lineage + CON exact lineage schema
  -> CON participant with ordered flush-only reviewer and submitter operations
  -> REV-10 first canonical Review-committing transaction

CON core hidden-readiness manifest + REV-12
  -> REV-12A hidden joint release control
  -> named AUTH action activation gates after hidden behavior
  -> REV-13 joint product release
```

Optional contribution-evidence projection work is not on this critical path.

## Reconciliation Result

- Every valid Review creates one reviewer contribution. When its decision is
  `accept`, REV also creates FinalAcceptance and CON creates exactly one
  submitter contribution from that fact.
- Frozen ContributionPolicyVersion rules, not guide context or an adapter,
  decide unpaid/payable eligibility.
- Core creation makes no ART call and uses no external adapter.
- Money and project-points adapters fulfill already-created awards; they never
  decide eligibility.
- Shared outbox claim ownership remains with the dispatcher.
- REV stages shared audit and outbox rows after the reviewer operation and the
  applicable decision branch, including the submitter operation for `accept`.
  The request route or service command owns the caller `AsyncSession` and only
  commit; CON returns typed staging inputs and never commits.
- REV owns no CON public route, policy, award, fulfillment, or projection state.
- All runtime gates must be reread from their exact merged trusted-main SHAs.
