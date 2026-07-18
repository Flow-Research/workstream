# Chunk Contract: WS-REV-001-10

## Goal

Install the exact merged CON flush-only contribution/award participant and
create the first hidden service capable of committing a canonical Review and
the FinalAcceptance created for an `accept` Review atomically with task,
contribution, award, audit, and outbox effects. Production routes remain absent.

## Risk class

L1 canonical judgment, contribution/conditional-compensation, and composition
integrity.

## Allowed files

```text
backend/app/modules/reviews/{schemas,service,router}.py
backend/app/composition/review_lifecycle.py only to install the exact merged CON participant
backend/tests/test_{reviews,contributions,compensation,authorization,api_contract_e2e}.py
backend/scripts/api_contract_e2e.py
docs/operations_reviewer_workflow.md
docs/operations_payment_reputation.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-10.json
```

## Not allowed

```text
new contribution policy, rule, award, fulfillment, or projection behavior in review code
ContributionRecordRequested compatibility event
optional or no-op CON participant
ART capability call, provider I/O, or contribution-evidence artifact write in the transaction
production `/api/v1` review-router registration
CON router, repository, policy, outbox, award, fulfillment, or projection edits
submitter contribution for needs_revision or reject
submitter contribution inferred directly from Review.decision
manual/public FinalAcceptance create route or separate authorization action
CON-owned commit or shared audit/outbox staging
reputation scoring
```

## Acceptance criteria

- `review.decision` uses AUTH's prepared mutation protocol: AUTH locks exact
  reviewer authority and creates an opaque, non-Pydantic, single-use handle
  bound to exact session, ActionId, reviewer actor-reference kind and ID,
  idempotency key, and canonical request digest; REV locks idempotency, queue,
  lease, task, assignment,
  versioned Submission, predecessor Review, and packet/evidence facts; REV
  recomposes final context and calls AUTH; AUTH validates every binding/current
  authority, consumes once, evaluates once, and stages evidence before the first
  feature mutation; REV appends
  the immutable Review, findings, and resolutions; consumes the lease; closes
  the queue entry; and then calls the CON reviewer operation. That operation
  creates `completed_review` and evaluates the reviewer policy. REV then applies
  the decision branch. For `accept`, REV appends FinalAcceptance, sets Task to
  `accepted`, and sets TaskAssignment to `completed` before calling the CON
  submitter operation. That operation creates `accepted_submission` and
  evaluates the submitter policy. REV stages shared audit and outbox rows, and
  the request route or service command commits once. Wrong-binding, serialized,
  forged, or caller-constructed attempts against an unconsumed handle stage no
  AuthorizationDecision/evidence, preserve the legitimate handle, and permit its
  later exact first use. Stale/already-consumed and concurrent duplicate attempts
  remain invalid and stage no new state. Current-authority
  or policy denial after valid consumption follows AUTH's clean denial-evidence
  protocol and leaves no Review, lifecycle, CON, or feature/shared audit/outbox
  mutation.
  This hidden service has no public route or background-command entry point.
  REV-12A later installs the mandatory lifecycle fence before REV-13 releases
  any decision surface.
- Every committed review decision creates exactly one reviewer
  `contribution_type=completed_review` directly from Review and ReviewLease.
  Every Review, submitted finding, and resolution is immutable for all three
  decisions. When the decision is `accept`, REV also creates exactly one
  immutable same-chain FinalAcceptance and CON creates exactly one submitter
  `contribution_type=accepted_submission` from that fact plus TaskAssignment.
  `needs_revision` and `reject` create no FinalAcceptance or submitter record.
- Reviewer contributions require `source_review_id` and
  `source_review_lease_id`, with `source_final_acceptance_id` and
  `source_task_assignment_id` null. Submitter contributions require
  `source_final_acceptance_id` and
  `source_task_assignment_id`, with direct `source_review_id` and
  `source_review_lease_id` null. PostgreSQL checks enforce these mutually
  exclusive shapes, one `completed_review` per Review, and one
  `accepted_submission` per FinalAcceptance.
- `FinalAcceptance` uses the exact REV-04 schema and constraints: unique task,
  source Review, and Submission; exact accepted submitter, recording reviewer,
  project/task, and immutable ReviewPolicy context. It is created only as an
  internal consequence of the authorized accept path, with no separate action
  or API.
- One mandatory typed CON participant exposes two ordered flush-only operations
  using the caller's AsyncSession. The reviewer operation receives locked Review,
  ReviewLease, Submission, canonical reviewer, project and task, originating
  AuthorizationDecision, request and correlation references, and the lease-frozen
  reviewer ContributionPolicyVersion. The submitter operation is called only
  after FinalAcceptance exists for `accept`; it additionally receives that fact,
  TaskAssignment, canonical submitter, and the assignment-frozen submitter
  ContributionPolicyVersion. There is no omnibus input with nullable
  FinalAcceptance or both actors' policy contexts.
- A separately approved and merged ART/task-owner amendment to the current
  submission/checker cutover has persisted server-derived verified
  `Submission.artifact_hash` on the existing versioned Submission. CON copies it
  to `ContributionRecord.artifact_hash`. Caller `package_hash`, a renamed
  source-digest field, or a live ART lookup cannot substitute.
- Database and transaction validation requires consistency among Review,
  reviewer, and ReviewLease; consistency among FinalAcceptance, Review,
  Submission, ReviewPolicy, and actors; consistency between the Submission
  contributor and TaskAssignment; and same-project and same-task lineage.
  Current TaskAssignment, current project policy, direct `Review.decision`
  inference, or caller-supplied actor/hash facts cannot substitute.
- CON evaluates the frozen ContributionRule. Explicit unpaid creates no award;
  payable creates immutable money and/or project-points CompensationAward rows.
  Adapters fulfill awards after commit and never decide eligibility.
- Derived inserts inside `review.decision` do not invent
  `contribution.materialize` or `compensation.award.materialize` actions.
- Review, submitted findings, and resolutions for every decision,
  FinalAcceptance when the decision is `accept`, ReviewEvidenceArtifact links,
  queue and lease state, Task and TaskAssignment effects, contributions, awards,
  audit, and shared-outbox rows commit or roll back together. CON flushes only
  its contribution and award rows, returns typed audit and outbox inputs, never
  commits, and performs no network or provider I/O. REV stages the shared rows.
- CON failure rolls back the entire decision. No no-op participant, post-commit
  canonical contribution repair, or Review-only success path exists.
- Fault injection after the reviewer contribution and policy evaluation but
  before every branch effect, after FinalAcceptance, after each accepted Task or
  TaskAssignment effect, and after the submitter contribution and policy
  evaluation proves that the reviewer operation cannot commit independently
  and that no partial decision survives.
- Exact replay duplicates no Review, FinalAcceptance, contribution, award,
  audit, or outbox row; changed replay conflicts. Replay reauthorizes result
  disclosure.
- Independent Postgres barriers cover decision versus expiry, reviewer
  revocation, binding-state drift, and duplicate/changed replay in both orders.
  Fault injection after every REV, task, CON, audit, and outbox stage proves
  zero partial state and bounded database retry behavior.
- Initial revision-preparation failure on `needs_revision` rolls back Review,
  Task and TaskAssignment, lease, preparation, reviewer contribution and award,
  audit, and outbox state together.
- Same-reviewer and takeover matrices prove v1 `needs_revision` then v2
  accept/reject follows exact Submission/Review predecessors, attributes each
  reviewer record to the actual Review author. The v1 Review/findings remain
  unchanged, and only accepted v2 creates FinalAcceptance and its submitter
  record.
- Forward/backward guide rebase leaves TaskAssignment ContributionPolicyVersion
  unchanged; each Review uses its lease freeze; reviewer award eligibility is
  decision-neutral for the same frozen rule.
- Chain reads expose bounded relationship metadata only. Historical artifact
  bytes remain inaccessible without the active exact packet manifest.
- Internal API contracts use `/api/v1` and stable errors, but production OpenAPI
  proves every lifecycle route absent.
- Every ReviewService construction uses the single fail-closed composition with
  the exact merged CON participant. Review services import no concrete CON or
  ART implementation.
- This chunk supplies hidden decision behavior and its feature-manifest delta.
  `WS-AUTH-001-REV-08` activates `review.decision` only after this chunk's full
  REV+CON composition merges; REV-13 later exposes the route. This chunk changes
  no action availability.
- Optional contribution-evidence projection is outside this chunk and outside
  core release readiness. Its absence/outage cannot affect canonical truth.

## Verification

```text
cd backend && pytest -q tests/test_reviews.py tests/test_contributions.py tests/test_compensation.py tests/test_authorization.py tests/test_api_contract_e2e.py
cd backend && ruff check app/modules/reviews app/composition/review_lifecycle.py tests/test_reviews.py
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
cd backend && for path in 'app/modules/reviews/*' app/composition/review_lifecycle.py; do coverage report --include="$path" --precision=2 --fail-under=90 || exit 1; done
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, and test-delta.

## Human review focus

AUTH-first lock/evaluation order, FinalAcceptance uniqueness and exact immutable
lineage, mandatory CON participant, REV-owned audit/outbox staging, no ART call,
contribution creation matrix, replay, rollback, and route absence.

## Stop condition

Merge, record automated memory, and stop. Do not start 11.
