# Chunk Contract: WS-REV-001-03A2 — Lease And Preference Persistence

## Status

Active implementation contract refreshed from `main` at `e2057d0f` after
merged REV-03A1 PR #262 and CON-03B PR #274.

## Parent initiative

`WS-REV-001` — Review And Revision Lifecycle.

## Goal

Persist immutable ReviewLease attempt identities and enforce the existing queue
preference actor boundary with PostgreSQL-backed active-capacity invariants,
without implementing claim, release, decline, expiry, selection, or any public
behavior.

REV owns every lease row, constraint, timestamp, and later transition. This
chunk consumes only CON's canonical `contribution_policy_versions(id,
project_id)` foreign-key target; it neither selects policy nor imports CON
repositories or behavior.

## Why this chunk exists

Lease attempt history, reviewer capacity, frozen reviewer policy identity, and
preference actor integrity form one L1 concurrency boundary separate from queue
admission and later claim choreography.

## Risk class and SLA

L1 database concurrency and immutable cross-domain economic lineage. No
expedited SLA.

## Allowed files

```text
backend/app/modules/reviews/models.py
backend/app/modules/reviews/schemas.py
backend/app/modules/reviews/repository.py
backend/app/db/models.py (ReviewLease metadata registration only)
backend/alembic/versions/0056_review_lease_preference.py
backend/tests/test_review_lease_persistence.py
backend/tests/test_review_queue_persistence.py (preference-integrity regression only)
backend/tests/test_alembic.py
backend/tests/conftest.py (reset inventory/schema fingerprint only)
backend/scripts/run_test_lanes.py (new test-module lane registration only)
backend/tests/test_ci_test_lanes.py (lane registration assertion only)
docs/architecture_data_model.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/CHUNK_MAP.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/STATUS.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/chunks/WS-REV-001-03A2-lease-preference-persistence.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/reviews/WS-REV-001-03A2-*.md
```

Migration `0056_review_lease_preference` is the exact successor of merged
`0055_contribution_policy`.

## Not allowed changes

- No route, service, AUTH evaluation, grant lookup, queue selection, claim,
  release, decline, expiry job, lazy recovery, packet manifest, Review,
  finding, decision, revision, audit, outbox, ART operation, or CON operation.
- No callable queue-state transition. This schema chunk adds the reserved
  `leased` state and exact `active_lease_id` relationship promised by 03A1;
  queue claim choreography remains in 06A.
- No policy lookup or moving selector. Callers of the later claim command will
  supply the already-selected canonical policy-version ID.
- No CON model duplication, nullable/conditional policy FK, compatibility
  alias, placeholder table, contribution record, award, or compensation logic.
- No action activation, router registration, frontend behavior, historical
  backfill, or upstream row mutation.

## Persistence shape

Each `ReviewLease` stores:

- UUID identity and exact queue/project/task/Submission/version lineage;
- canonical human reviewer `ActorProfile.id`;
- immutable non-null reviewer `ContributionPolicyVersion.id` with same-project
  composite FK;
- positive per-queue attempt generation;
- status `active | consumed | released | expired | revoked`;
- database-written `claimed_at`, caller-bounded future `expires_at`, and
  terminal `closed_at`/`close_reason` provenance.

Close reasons are `review_recorded | manual_release | lease_expired |
grant_revoked | admin_override` and must match their terminal status.

## Acceptance criteria

- PostgreSQL partial unique indexes permit at most one active lease per queue
  entry and one active lease globally per reviewer.
- `ReviewQueueEntry` gains `leased` and an exact active-lease pointer. Deferred
  database integrity requires active lease, leased queue state, and the
  queue-local pointer to agree at transaction commit while still permitting a
  later atomic claim command to stage both rows in either safe write order.
- Queue lineage is enforced through the exact 03A1 composite queue identity;
  crossed project/task/Submission/version values are rejected.
- Every lease stores an immutable, non-null same-project FK to CON's canonical
  `ContributionPolicyVersion`; REV neither duplicates fields nor selects a
  substitute source.
- Inserted attempts begin active, use database `claimed_at`, have
  `expires_at > claimed_at`, and use a unique positive generation per queue.
  The database rejects a draft or already-retired version at insertion;
  CON-06 still owns claim-time lookup and selection of that published identity.
- Reviewer and preferred-reviewer references must resolve to canonical human
  ActorProfiles; service actors are rejected by database guards.
- Lease identity, reviewer, frozen policy, lineage, generation, claimed time,
  and expiry never change. Terminal attempts are wholly immutable and cannot
  reopen; active-to-terminal state shapes retain exact close provenance.
- Existing `ReviewQueueEntry.first_queued_at` remains immutable and independent
  from `available_since`, `preference_expires_at`, and lease expiry.
- Repository methods only add/flush caller-transaction persistence records;
  they do not commit, authorize, select, claim, update the queue pointer, or
  perform lifecycle transitions.
- Migration performs no historical backfill, changes no existing queue state,
  and refuses downgrade while lease rows exist.
- No route is registered and every review lifecycle action remains unavailable.

## Verification commands

```text
cd backend && .venv/bin/alembic heads
cd backend && .venv/bin/pytest -q tests/test_alembic.py -k review_lease_preference
cd backend && .venv/bin/pytest -q tests/test_review_lease_persistence.py tests/test_review_queue_persistence.py
cd backend && .venv/bin/pytest -q tests/test_ci_test_lanes.py
cd backend && .venv/bin/ruff check app/modules/reviews tests/test_review_lease_persistence.py tests/test_review_queue_persistence.py tests/test_alembic.py tests/test_ci_test_lanes.py scripts/run_test_lanes.py
cd backend && .venv/bin/pytest --cov=app.modules.reviews --cov-branch --cov-report=term-missing --cov-fail-under=90 -q tests/test_review_lease_persistence.py tests/test_review_queue_persistence.py
python3 scripts/check_stale_review_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

GitHub Actions owns the full sharded suite and repository-wide coverage floor.
Local proof remains focused on this chunk.

## Required reviewers

Architecture, security/auth, product/ops, QA/test, senior engineering,
reuse/dedup, docs, test-delta, and CI integrity.

## Human review focus

Partial uniqueness, exact queue and CON policy-version composite FKs, canonical
human actor enforcement, immutable attempt history, terminal provenance,
timer separation, downgrade safety, and absence of claim behavior.

## Stop conditions

Stop if implementation requires policy selection, a CON write, AUTH evaluation,
callable queue claim choreography, or a foreign schema change. Merge and stop
before packet persistence or claim behavior.
