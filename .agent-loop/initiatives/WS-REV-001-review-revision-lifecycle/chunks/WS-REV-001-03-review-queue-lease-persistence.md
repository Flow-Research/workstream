# Chunk Contract: WS-REV-001-03

## Goal

Add review-owned queue and permanent lease-attempt persistence with complete
database invariants and repository tests, but no public claim behavior.

Chunk start requires the WS-CON `ContributionPolicyVersion` persistence contract to be
merged with its exact lease-freeze FK/field types. This chunk owns those exact
immutable references on `ReviewLease`; it does not invent or implement WS-CON
policy.

## Risk class

L1 schema and concurrency foundation.

## Allowed files

```text
backend/app/modules/reviews/{__init__,models,repository}.py
backend/app/modules/checkers/models.py only for CheckerRun composite identity
backend/app/db/models.py
backend/alembic/versions/<activation-next>_review_queue_lease.py
backend/tests/test_{alembic,reviews,checkers}.py
docs/operations_queue_policy.md only for deployment/backfill/rollback/remediation notes
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-03.json
```

## Not allowed

```text
public routes or Celery workers
Review, finding, response, or resolution records
task status mutations
grant reads or authorization logic
artifact provider calls
WS-CON implementation
```

## Acceptance criteria

- At most one queue entry per Submission version, and only an authoritatively
  admitted version may receive one.
- Every queue entry stores an immutable `admitting_checker_run_id`. CheckerRun
  exposes a composite `(id, submission_id)` identity so a composite FK binds the
  run to the queue's same Submission. A deferred insert constraint requires that
  run to be finalized, successful, current at that admission transaction, and
  `allow_review`; immutable finalized outcome fields preserve the admission
  fact. Later checker retry/supersession cannot rewrite the queue anchor.
  Ambiguous historical rows remain unqueued for remediation.
- Queue state/routing/preference/active-lease/closure compatibility has database
  check constraints.
- Lease state/close-reason compatibility has database check constraints.
- Partial unique indexes allow one active lease per queue and one globally per
  reviewer.
- Preferred reviewer and lease reviewer FKs reference canonical human
  `ActorProfile.id`; direct SQL cannot store external subjects, email, legacy
  profile row IDs, or service/system actors as reviewers.
- This uses the plan's composite actor-kind constraint or reviewed deferred
  trigger pattern; a plain ActorProfile FK does not satisfy the criterion.
  Direct-SQL tests cover service ActorProfile, system principal, external
  subject, legacy profile ID, and crossed human actor attempts.
- `first_queued_at` and permanent lease attempt history cannot be silently
  overwritten or deleted.
- Frozen contribution-policy identifiers/versions required by the approved
  WS-CON contract are persisted as exact immutable
  `ContributionPolicyVersion` references on each lease attempt. They are not
  part of the Submission guide/checker context and are never rebased with it.
- `ReviewPacketManifest` persistence is defined as an immutable lease-scoped
  semantic projection. Its base schema can name the exact queue, lease,
  Submission/version, admitting CheckerRun/results, locked guide/policy context
  digest, response-evidence relation set, and ART binding ID set. It stores no
  bytes, digest of artifact content, provider/scratch/receipt data, or AUTH
  matrix facts. Chunk 06 creates manifests atomically with leases; 09A may add a
  constrained revision-preparation reference without rewriting prior manifests.
- The schema migration performs no blanket historical queue backfill. Ambiguous
  existing submissions remain unqueued; later admission/reconciliation is
  limited by D13 and produces explicit audit/remediation evidence.
- Repository lock and deterministic ordering primitives are tested on Postgres.
- Deployment notes define ordering, no-backfill behavior, ambiguous-row
  remediation, rollback limits, and proof queries.

## Verification

```text
cd backend && alembic upgrade head
cd backend && pytest -q tests/test_alembic.py tests/test_reviews.py tests/test_checkers.py
cd backend && ruff check app/modules/reviews app/modules/checkers/models.py tests/test_reviews.py tests/test_checkers.py tests/test_alembic.py
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
cd backend && for path in 'app/modules/reviews/*' app/modules/checkers/models.py; do coverage report --include="$path" --precision=2 --fail-under=90 || exit 1; done
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, and test-delta.

## Human review focus

Partial uniqueness, state compatibility, immutable queue age, and migration
behavior under existing submissions.

## Stop condition

Merge, record automated memory, and stop. Do not start 04.
