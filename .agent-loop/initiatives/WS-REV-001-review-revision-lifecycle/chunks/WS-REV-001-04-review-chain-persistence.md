# Chunk Contract: WS-REV-001-04

## Goal

Add persistence for immutable Review records, immutable submitted findings and
resolutions, and the immutable FinalAcceptance created only for an `accept`
Review, together with submitter responses, evidence relations, decision
idempotency, and projection requests.

Chunk start requires the merged shared transactional-outbox contract. All
projection requests below use that shared foundation.

## Risk class

L1 schema, audit, and evidence ownership.

## Allowed files

```text
backend/app/modules/reviews/{models,repository,schemas}.py
backend/app/modules/tasks/models.py only for relationships/FKs
backend/app/db/models.py
backend/alembic/versions/<activation-next>_review_chain.py
backend/tests/test_{alembic,audit,reviews}.py
docs/operations_reviewer_workflow.md only for deployment/rollback/immutability notes
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-04.json
```

## Not allowed

```text
public routes, decision service, task effects, or background jobs
artifact provider implementation
grant or permission implementation
contribution/compensation models
mutable Review/finding/resolution rows
manual/public FinalAcceptance creation
review-private outbox or delivery queue
```

## Acceptance criteria

- One Review per Submission and synchronized predecessor-chain constraints.
- Every Review is immutable regardless of whether its decision is `accept`,
  `needs_revision`, or `reject`. Every submitted ReviewFinding and every later
  FindingResolution is immutable. A later review round appends new rows and
  never updates prior judgment or findings.
- `FinalAcceptance` is an immutable internal REV record with canonical
  `submission_id` implementing the conceptual Submission-version identity,
  `project_id`, `task_id`, `source_review_id`, `accepted_submitter_id`,
  `accepted_at`, `recorded_by`, and `policy_context_ref` constrained to the
  exact immutable ReviewPolicy row matching the reviewed Submission context.
  `accepted_submitter_id` is the canonical human `ActorProfile.id` shared by the
  reviewed Submission and its exact TaskAssignment. `recorded_by` is the
  canonical human `ActorProfile.id` shared by the source Review and ReviewLease.
- PostgreSQL enforces `UNIQUE(task_id)`, `UNIQUE(source_review_id)`, and
  `UNIQUE(submission_id)`, plus same-chain project/task/Submission/Review,
  accepted-submitter and TaskAssignment lineage, recording-reviewer and
  ReviewLease lineage, exact ReviewPolicy context, and canonical-human-actor
  integrity. Direct-SQL tests cross each actor and lineage independently; none
  may update or delete the record or create a crossed acceptance.
- This persistence chunk exposes no service, route, action, or background
  command capable of creating FinalAcceptance. Only REV-10 may append it, and
  only in the same transaction that appends a new Review whose decision is
  `accept`, after the mandatory CON participant has merged.
- `ReviewEvidenceArtifact` is an immutable REV semantic relation over one
  finalized ART binding. Before decision it is identified by exact lease,
  operation kind, evidence slot, and idempotency identity; after decision it may
  be linked set-once to the exact ReviewFinding or SubmissionFindingResponse.
  Binding identity and scope never change. This is not artifact byte storage,
  a provider reference, or a mutable ReviewAttempt.
- `Review.reviewer_id` is the exact canonical human `ActorProfile.id` on its
  ReviewLease; a composite constraint rejects a crossed lease/reviewer and no
  external subject, email, legacy profile ID, service actor, or system principal
  may be persisted as the human reviewer.
- Database constraints require `Review(Sn).prior_review_id` to identify the
  Review whose Submission is `Submission(Sn).supersedes_submission_id`; crossed
  task, version, Submission, or Review predecessor chains fail under direct SQL.
- Immutable findings use only blocking/advisory severity.
- Finding responses and resolutions are immutable and uniquely scoped.
- Evidence relation rows reference canonical ArtifactBinding IDs and are unique.
- Decision idempotency completes only with one canonical Review and, for accept,
  exactly one FinalAcceptance; it detects changed payload reuse.
- `ReviewDecisionRequest` reuses `canonical_json_hash`, shared request and
  correlation identifiers, and the reserve/lock/complete transaction shape,
  while keeping a review-specific operation/response matrix. No cloned JSON
  canonicalizer or second generic idempotency framework is added.
- One canonical shared-outbox projection event commits with Review. Shared
  outbox delivery state and ART receipts are reused; no review-private
  projection request/status table exists.
- The reject-Review reference on TaskAssignment is added now that the Review
  table exists and is constrained to a reject Review for the same task/current
  assignment.
- Database triggers or equivalent guards prevent prohibited update/delete of
  canonical review-chain records.
- Review events append through the merged shared AuditEvent participant in the
  caller transaction. No `ReviewAuditEvent`, review-private audit repository, or
  commit-owning audit writer exists.
- Deployment notes define ordering, historical-row handling, rollback limits
  after immutable rows exist, and proof queries without synthetic backfill.

## Verification

```text
cd backend && alembic upgrade head
cd backend && pytest -q tests/test_alembic.py tests/test_audit.py tests/test_reviews.py
cd backend && ruff check app/modules/reviews app/modules/audit tests/test_reviews.py tests/test_audit.py tests/test_alembic.py
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
cd backend && for path in 'app/modules/reviews/*' app/modules/tasks/models.py; do coverage report --include="$path" --precision=2 --fail-under=90 || exit 1; done
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, and test-delta.

## Human review focus

Immutability enforcement, FinalAcceptance uniqueness/cross-chain integrity,
predecessor integrity, evidence ownership, and idempotency atomicity.
Multi-version/takeover chain negatives receive explicit human attention.

## Stop condition

Merge, record automated memory, and stop. Do not start 05.
