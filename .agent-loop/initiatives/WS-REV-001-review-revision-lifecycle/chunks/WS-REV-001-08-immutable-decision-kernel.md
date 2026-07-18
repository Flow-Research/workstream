# Chunk Contract: WS-REV-001-08

## Goal

Freeze the immutable review-decision request, pure validation, task-effect
participant, lock/fact contract, the FinalAcceptance consequence of `accept`,
and the two operation-specific CON participant inputs. Do not create a
canonical Review-committing service, including the additional FinalAcceptance
write for `accept`, before CON merges.

## Risk class

L1 canonical judgment and transaction integrity.

## Allowed files

```text
backend/app/modules/reviews/{repository,schemas,service}.py
backend/app/modules/tasks/{models,review_participant}.py only for caller-transaction decision effects
backend/app/composition/review_lifecycle.py only to install the exact task participant
backend/tests/test_{reviews,tasks,authorization,artifacts,audit}.py
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-08.json
```

## Not allowed

```text
public decision route
production no-op WS-CON participant
any code path that commits a canonical Review, or an accept-path FinalAcceptance,
without the exact CON participant
remote storage calls inside the transaction
mutation of prior Submission, Review, ReviewFinding, or FindingResolution
reputation or fulfillment logic
```

## Acceptance criteria

- The frozen transaction contract rechecks exact reviewer grant, lease ownership/
  expiry, no-self-review, queue state, idempotency, predecessor chain, packet
  manifest, evidence relations, and stabilized binding facts using database time.
- The command declares planned `review.decision`. Mutation choreography is AUTH
  prepare/authority lock -> opaque, non-Pydantic, single-use handle bound to the
  exact session, ActionId, reviewer actor-reference kind and ID, idempotency key,
  and canonical request digest -> REV locks and final fact recomposition -> AUTH
  validates exact bindings/current authority, consumes once, evaluates once, and
  stages evidence before the first feature mutation -> REV appends the Review,
  findings, and resolutions -> CON
  reviewer operation -> REV decision branch -> CON submitter operation only for
  `accept` -> REV audit and outbox staging -> request route or service command
  commits once. No plain mutation-time `require()` or serialized authorization
  handle substitutes. Wrong-binding, forged, serialized, or caller-constructed
  attempts against an unconsumed handle fail before mutation, stage no
  AuthorizationDecision/evidence, preserve the legitimate handle, and permit its
  later exact first use. Stale/already-consumed and concurrent duplicate attempts
  remain invalid and stage no new state. Current-authority or policy denial after
  valid consumption follows AUTH's clean denial-evidence protocol and leaves no
  Review, lifecycle, CON, or feature/shared audit/outbox mutation.
- Decision, finding, evidence, and resolution rules match the canonical spec.
- Task effects use the task-owned `TaskReviewEffectsParticipant` with the
  caller's AsyncSession. It flushes without commit, reuses TaskRepository and
  lifecycle guards internally, and is the only path for review-driven task or
  assignment effects; review code never imports TaskRepository.
- Common effects append one immutable Review and every submitted immutable
  finding and resolution, consume the ReviewLease, close the ReviewQueueEntry,
  and invoke the mandatory CON participant's reviewer operation. That operation
  creates `completed_review` and evaluates the reviewer policy. Accept then
  appends FinalAcceptance, targets the Task state `accepted`, completes the
  TaskAssignment, and invokes the participant's submitter operation. Needs revision appends no
  FinalAcceptance, keeps the assignment active, targets `needs_revision`, and
  invokes no submitter operation. Human reject appends no FinalAcceptance,
  blocks only that assignment, targets canonical `rejected` with reason, and
  invokes no submitter operation.
  Administrative closure is not a decision.
- Every decision appends one immutable Review and any submitted immutable
  findings and resolutions before the reviewer contribution operation. The `accept`
  branch later prepares one same-chain immutable FinalAcceptance;
  `needs_revision` and `reject` prepare none and cannot invoke the submitter
  operation.
  No separate FinalAcceptance authorization action or public/manual creation
  contract exists.
- One mandatory typed CON participant exposes two ordered flush-only operations
  in the caller's AsyncSession. The reviewer operation always receives exact
  Review and ReviewLease facts, creates the reviewer contribution, and evaluates
  the reviewer policy. The submitter operation is called only after REV creates
  FinalAcceptance for `accept`; it receives FinalAcceptance and TaskAssignment
  facts, creates the submitter contribution, and evaluates the submitter policy.
  Neither input uses nullable FinalAcceptance or combines both actors' frozen
  policy contexts. Both operations return typed audit and outbox staging inputs
  and never commit.
- Pure tests prove the future atomic write set: immutable Review and submitted
  findings and resolutions for every decision, FinalAcceptance for `accept`,
  ReviewEvidenceArtifact links, queue and lease state, Task and TaskAssignment
  effects, CON contributions and awards, REV-staged audit records, and outbox
  records. This chunk does not expose a service capable of committing that set.
- Exact replay contract returns the Review after REV-10; changed replay fails.
- Idempotency is bound to actor, operation, lease, submission, and canonical
  payload. Replay reauthorizes disclosure for the same actor without requiring
  a consumed lease to remain active; cross-actor, revoked-disclosure, or changed
  payload replay fails without revealing the prior result.
- The decision actor is the active canonical human `ActorProfile.id` that owns
  the exact ReviewLease. UUID shape alone is insufficient; a service actor,
  system principal, legacy ID, or external subject cannot decide a Review.
- No hidden or production composition can commit a Review before the exact CON
  participant is installed. The same rule covers the additional FinalAcceptance
  write on the `accept` path. Absence of either ordered CON operation fails
  construction; no optional or no-op path exists.
- This chunk proves command-specific lock planning and the task participant. Full
  decision races, participant rollback, and canonical commits move to REV-10
  after CON merges.
- Audit, outbox, dead-letter, alerts, and error details contain only bounded
  typed projections: no finding body, private artifact metadata, signed access,
  provider path, or unrestricted identity value.
- Audit uses the shared caller-transaction participant with request/correlation
  and AuthorizationDecision linkage; no review-private audit persistence exists.

## Verification

```text
cd backend && pytest -q tests/test_reviews.py tests/test_tasks.py tests/test_authorization.py tests/test_artifacts.py tests/test_audit.py
cd backend && ruff check app/modules/reviews app/modules/tasks tests/test_reviews.py tests/test_tasks.py
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
cd backend && for path in 'app/modules/reviews/*' app/modules/tasks/models.py app/modules/tasks/review_participant.py app/composition/review_lifecycle.py; do coverage report --include="$path" --precision=2 --fail-under=90 || exit 1; done
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
reuse/dedup, and test-delta.

## Human review focus

Complete decision contract and FinalAcceptance consequence, no premature
canonical commit, route absence, and no contribution or storage side-effect gap
hidden by tests.

## Stop condition

Merge, record automated memory, and stop. Do not start 09A.
