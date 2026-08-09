# Chunk Contract: WS-ART-001-04C2 — Ready Admission Publication

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Active after merged 04C1

## Goal

Publish one immutable capacity-charged ready admission after exact read-back
verification and compose the hidden continuous contributor endpoint.

## Allowed Files

Only these implementation surfaces may change:

- `backend/app/modules/artifacts/models.py` and the next linear Alembic migration;
- the existing canonical `SubmissionBundlePreparationRequest` and port in
  `backend/app/interfaces/artifact_operations.py`;
- `backend/app/modules/artifacts/repository.py`;
- one narrow submission-admission publisher module under
  `backend/app/modules/artifacts/` and its composition call from
  `backend/app/modules/artifacts/service.py`;
- the existing `backend/app/modules/artifacts/pre_submit_evidence.py` only to
  derive and persist the admission's database-verifiable locked-context hash;
- the existing hidden submission preparation composition under
  `backend/app/modules/artifacts/`, the existing
  `backend/app/adapters/artifacts/` composition root, and
  `backend/app/modules/tasks/router.py`; TASK-owned locked preparation-plan
  projection may change only in
  `backend/app/modules/tasks/pre_submit_context.py`;
- bounded admission-usage projection fields in
  `backend/app/modules/artifacts/operator.py` and
  `backend/app/modules/artifacts/router.py`;
- directly corresponding tests, CI lane inventory, ART specification/data-model
  documentation, and this initiative's status/review evidence.

## Not Allowed Changes

Submission/binding consumption, public activation, expiry/release/delete,
candidate storage, review/contribution, or new recovery machinery. Do not
change AUTH catalogue, grants, constraints, evaluators, or action availability;
legacy `TaskService` Submission creation; provider adapters; scanners; recovery
aggregates; or create a second verification path.

## Acceptance Criteria

Only verified matching bytes publish `ready`. The generic verifier calls one
narrow submission-admission publisher only from its verified terminal
transaction. The publisher locks and reloads the exact
`SubmissionBundleDurableIntent`, its passing/eligible `PreSubmitEvidenceSet`,
generic put attempt, verified `ArtifactContent`, verified `ArtifactReplica`,
and mandatory successful `ArtifactVerificationReceipt` as the sole durable
publication lineage. It also records whichever provider-write evidence exists:
the nullable direct `ArtifactOperationReceipt` or nullable
`ArtifactPutObservationReceipt`. Exactly one of those write-evidence paths must
match the same put attempt and replica lineage. Guide and checker-output
verification remain unaware of submission lifecycle semantics beyond invoking
the typed publisher with durable identifiers.

The hidden POST composes 04A2-04C1 continuously in the request, returns only a
bounded operation/current-admission result, and never waits for or replaces the
durable verifier. Exact POST replay returns the same durable operation and, when
verification has already published it, the same admission. Ready publication
may therefore occur after the request returns. No scratch path, prepared handle,
byte stream, or process-local capability crosses into the verification job or
publisher.

04C2 creates only `ready`. Its schema defines the complete
`ready -> consumed|stale` terminal shape, immutable actor/link/project/task/
assignment/predecessor/context/manifest/evidence lineage, and uniqueness needed
for later consumption, but 04C2 does not execute `consumed` or `stale`
transitions and does not create a Submission or binding. Those mutations and
their final Submission-consumption uniqueness fence belong to 05A. Abandoned
ready admissions remain charged. Fixed pre-submit materializer authority is
already active; contributor preparation remains hidden and
`artifact.submission_bundle.prepare` remains planned/unavailable.

## Verification Commands

Focused verification/publication tests must cover direct acknowledgement,
observed-confirmed recovery, non-verified outcomes, replay, concurrent verified
publication, lineage mismatch, and no guide/checker admission side effect.
Schema tests prove immutable lineage and valid ready/consumed/stale shapes
without exercising 05A transitions. Operator tests prove bounded unbound-ready
and stale counts/bytes. Run Ruff, hosted gates, 90% owned subsystem coverage,
and the 78% repository baseline.

## Required Reviewers

Security/auth, architecture, QA, product/ops, senior, CI, docs, reuse, test delta.

## Human Review Focus And Stop Conditions

No bindable admission exists before complete verification; no abandoned state
causes product lifecycle effects.
