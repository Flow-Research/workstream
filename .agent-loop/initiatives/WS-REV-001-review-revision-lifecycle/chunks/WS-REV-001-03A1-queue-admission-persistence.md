# Chunk Contract: WS-REV-001-03A1 — Queue And Admission Persistence

## Parent initiative

`WS-REV-001` — Review And Revision Lifecycle.

## Goal

Add the smallest hidden REV-owned persistence foundation for one queue identity
per exact reviewable Submission and one idempotent admission operation, without
wiring checker admission or exposing behavior.

## Why this chunk exists

Queue identity and database invariants are independently reviewable and do not
require final ART packet or CON interfaces. Separating them from leases avoids
one oversized concurrency migration.

## Risk class

L1 database identity, immutable lineage, and future concurrent admission.

## SLA

No expedited SLA.

## Allowed files

Current main now has the single ART-owned head `0050_guide_source_v2`. After
rebasing PR #262, this chunk owns its exact successor
`0051_review_queue_foundation.py` and the following scope:

```text
backend/app/modules/reviews/__init__.py
backend/app/modules/reviews/models.py
backend/app/modules/reviews/repository.py
backend/app/modules/reviews/schemas.py
backend/app/db/models.py (metadata registration only)
backend/alembic/versions/0051_review_queue_foundation.py
backend/tests/test_alembic.py
backend/tests/test_review_queue_persistence.py
backend/tests/conftest.py (schema fingerprint/fixture registration only)
backend/scripts/run_test_lanes.py (canonical lane registration only)
backend/tests/test_ci_test_lanes.py (lane registration assertion only)
docs/architecture_data_model.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-03A1.json
```

The preimplementation refresh must replace `<next>` and confirm exact metadata
registration conventions before code.

## Not allowed changes

- Checker completion hooks, task transitions, automatic admission, queue reads,
  selection, claims, leases, preferences, packets, Reviews, findings,
  FinalAcceptance, revision, routes, jobs, or action activation.
- AUTH, ART, TASK, CHECKER, CON, audit, or outbox implementation.
- Artifact bytes, provider identifiers, contribution fields, grant snapshots,
  or a competing Submission identity.

## Acceptance criteria

- `ReviewQueueEntry` references the exact existing Submission, Task, project,
  admitting CheckerRun identity slot, immutable first-queued time, routing and
  lifecycle generation fields needed by later behavior.
- Persistence supports open and preferred routing shapes but implements no
  transition or selection rule.
- A separate admission-idempotency identity can reserve/record one admission
  attempt without authorizing it or mutating upstream rows.
- Database constraints permit at most one queue identity per Submission and
  reject cross-project/task/Submission lineage.
- A REV-owned PostgreSQL write-time guard rejects any mismatch among stored
  project, task, Submission/version, and admitting CheckerRun identities. A
  pending queue or committed admission requires that exact CheckerRun to be
  completed, current for the Submission, and `allow_review`; no checker hook or
  automatic admission is added.
- No migration backfills historical submissions or fabricates CheckerRun/ART
  facts. Required foreign facts may remain unpopulated only in explicitly
  non-admitted setup shapes that cannot become pending.
- Queue history cannot be updated into a different Submission/task/project.
- Models contain no AUTH handle, token, grant query, ART locator/bytes, or CON
  state.
- No router is registered and every REV lifecycle action remains unavailable.
- 03A1 cannot persist `leased` or an active-lease reference. Those shapes enter
  only with the real REV-owned ReviewLease FK in 03A2.
- Admission idempotency enforces exact SHA-256 request digests, one replay
  namespace/operation identity, pending-without-queue and committed-with-queue
  shapes, and rejects conflicting reuse at the database boundary.

## Verification commands

Freeze exact node IDs at start. Minimum proof:

```text
cd backend && .venv/bin/alembic heads
cd backend && .venv/bin/pytest -q tests/test_alembic.py -k review_queue_foundation
cd backend && .venv/bin/pytest -q tests/test_review_queue_persistence.py
cd backend && .venv/bin/ruff check app/modules/reviews tests/test_review_queue_persistence.py tests/test_alembic.py
cd backend && .venv/bin/pytest --cov=app.modules.reviews --cov-branch --cov-report=term-missing --cov-fail-under=90 -q tests/test_review_queue_persistence.py
python3 scripts/check_stale_review_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

GitHub Actions runs the full sharded suite and repository coverage floor.
Focused PostgreSQL proof must include mismatched task/project/Submission/checker
refusal, non-final/non-current/non-`allow_review` refusal, immutable lineage and
first-queued time, replay conflicts, no historical backfill, and populated
downgrade refusal followed by an empty safe round trip.

## Required reviewers

Architecture, security/auth, product/ops, QA/test, senior engineering,
reuse/dedup, docs, test-delta, and CI integrity.

## Human review focus

One queue identity, exact existing Submission lineage, no fabricated admission,
no external ownership, direct-SQL constraints, and safe downgrade/refusal.

## Stop conditions

Stop if current main lacks an exact FK target required for queue identity, if
the migration would require modifying upstream-owned rows, or if admission
behavior becomes necessary. Merge and stop before 03A2.
