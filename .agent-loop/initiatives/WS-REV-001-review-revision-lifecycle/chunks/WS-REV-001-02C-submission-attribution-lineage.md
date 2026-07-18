# Chunk Contract: WS-REV-001-02C - Submission Attribution, Context, And Immutable Lineage

## Parent initiative

`WS-REV-001` - Review And Revision Lifecycle

## Goal

Bind every existing versioned Submission to the exact TaskAssignment and
canonical contributor that produced it, stamp the complete guide identity, and
enforce immutable immediate-predecessor and checker-remediation source lineage
after finalization.

## Why this chunk exists

Current Submission service logic allocates sequential versions, but direct SQL
can create cross-task or skipped predecessor chains and prior attribution can be
misread after reassignment. Checker-remediation N+1 currently has no immutable
causal relation to the needs-revision CheckerRun. The existing Submission must
become durable review lineage without introducing a competing SubmissionVersion
or lifecycle-root table.

## Risk class

L1 schema, migration, identity, and lineage.

## SLA

P2.

## Preconditions

- 02B is merged and automated memory is current.
- The exact merged AUTH contributor foundation is present: both models expose
  canonical `contributor_id`, retired contributor-identity storage names are
  absent, and database-backed
  human ActorProfile lineage is proven.
- The merged AUTH contract exposes the supported transaction-local
  canonical-active-human revalidation consumed by task submission. If it does
  not, 02C stops for an AUTH-owned amendment rather than querying actor/grant
  tables.
- 02A Task guide stamps and activation-sequence constraints are present.
- This contract receives a separate human start.

## Allowed files

```text
backend/app/modules/tasks/{models,schemas,repository,service}.py
backend/app/modules/checkers/{models,repository}.py only for the composite CheckerRun source key and lock/read support
backend/app/modules/checkers/service.py only if a CheckerRun supersession/retry path must adopt the shared Task-first source-lock prefix
backend/app/db/models.py
backend/alembic/versions/<then-current-next>_submission_attribution_lineage.py
backend/tests/test_{alembic,tasks,checkers}.py
.github/workflows/backend.yml only for persistent 90 percent task/checker lineage coverage gates
docs/architecture_data_model.md
docs/architecture_lifecycle_state_machine.md
docs/operations_revision_replay.md
docs/operations_operator_workflow.md only for migration/deployment/remediation
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-02C.json
```

## Not allowed changes

```text
new SubmissionVersion table or public submission route redesign
AUTH-owned contributor field rename, compatibility alias, or ActorProfile schema
ProjectGuide activation allocation, ReviewPolicy shape, or checker routing/outcome semantics
review queue, lease, Review, finding, response, preparation, or FinalAcceptance
ART artifact_hash cutover or provider calls
CON, compensation, contribution, reputation, adjudication, or synthetic reject
```

## Acceptance criteria

- Submission gains immutable non-null `task_assignment_id` and a composite
  same-task foreign key to `(TaskAssignment.id, TaskAssignment.task_id)`.
- Submission `contributor_id` must equal the exact referenced assignment's
  `contributor_id`. A database constraint trigger or equivalently reviewed
  composite key enforces direct-SQL parity without duplicating AUTH ownership.
- Existing rows backfill only when exactly one TaskAssignment satisfies this
  SQL-compatible predicate: same task and contributor;
  `assigned_at <= Submission.submitted_at`; non-null
  `accepted_at <= Submission.submitted_at`; and `released_at is null or
  Submission.submitted_at <= released_at`. Boundaries are inclusive, current
  assignment status is not historical evidence, and overlapping qualifying
  intervals are ambiguous. Zero or multiple candidates, null acceptance,
  timestamp ties that yield multiple candidates, or invalid interval ordering
  fail with task/submission IDs and remediation; current/recent assignment
  inference is prohibited.
- Assignment release, contributor authority loss, or reassignment never changes
  a prior Submission's assignment or contributor attribution.
- Submission stamps non-null `locked_guide_id`, `locked_guide_version`, and
  `locked_guide_activation_sequence` copied from the exact Task context used for
  that attempt. Same-guide composite integrity rejects mixed identities.
- Existing rows backfill guide ID/sequence only from their existing locked guide
  version and same-project Task context. Missing or inconsistent lineage fails
  rather than choosing the current active guide.
- `supersedes_submission_id` is null only for version 1. Version N greater than
  one points to version N-1 for the same task. Direct SQL rejects self-links,
  cross-task predecessors, skips, branches, and duplicate successors.
- Submission gains nullable, server-derived
  `remediation_source_checker_run_id`. It is null for version 1. Before the
  later human-preparation cutover, every version N greater than one references
  the exact completed, `needs_revision`, current-at-selection CheckerRun for its
  immediate predecessor Submission and same Task. A composite database relation
  plus constraint trigger or equivalently reviewed PostgreSQL enforcement
  rejects crossed task/predecessor/run facts, non-final or non-needs-revision
  sources, direct-SQL fabrication, and source deletion/mutation. The nullable
  source is unique, so one CheckerRun cannot admit two N+1 versions.
- Existing N greater than one rows backfill the checker source only when one
  completed needs-revision CheckerRun for the immediate predecessor is proven by
  matching task, predecessor, transition audit, and creation chronology. Zero or
  multiple candidates fail with task/submission/run IDs and remediation; current
  or latest-run inference is prohibited.
- Draft/staged submission fields required by current finalization/checker flows
  remain mutable only until the existing finalization boundary. After physical
  `Submission.locked_at` is set (publicly serialized as `finalized_at`),
  identity, task/assignment/contributor, version, predecessor, checker-remediation
  source, locked context, packet, evidence, and attestation fields are
  update/delete protected. Later ART-owned server-derived `artifact_hash`
  publication remains an explicitly allowed set-once extension and is not
  implemented here.
- Version allocation and predecessor selection lock the Task, current Submission
  chain head, then exact source CheckerRun. CheckerRun supersession/retry paths
  that can change source currentness acquire that same Task-first prefix before
  CheckerRun rows; same-type rows lock by ascending ID. Creation revalidates
  completed/current/needs-revision facts after all locks. Concurrent initial
  creates yield one v1 and an exact replay or stable conflict, never v2.
  Concurrent creation against one exact final needs-revision CheckerRun yields
  one N+1 and an exact replay or conflict, never N+2. A later CheckerRun retry
  does not invalidate or rewrite the committed source relation.
- TaskAssignment continues to store only task identity and contributor/freeze
  terms; it receives no guide or revision-preparation duplicate.
- Submission creation revalidates that the canonical contributor ActorProfile
  is active in the transaction through the supported AUTH-owned boundary.
  Suspended/deactivated humans, services, external subjects, emails, legacy
  profile IDs, and token-role values cannot substitute.
- No Review, queue entry, checker decision, contribution, or task terminal
  effect is created by migration or lineage enforcement.
- CI retains every existing gate and the repository-wide 78 percent baseline,
  and persistently enforces at least 90 percent coverage for the task/checker
  lineage files materially changed here.
- Downgrade refuses after rows depend on the new assignment/guide lineage unless
  the documented destructive remediation procedure is used.

## Verification commands

```text
cd backend && alembic upgrade head
cd backend && alembic heads
cd backend && pytest -q tests/test_alembic.py tests/test_tasks.py tests/test_checkers.py
cd backend && ruff check app/modules/tasks app/modules/checkers/models.py app/modules/checkers/repository.py app/modules/checkers/service.py tests/test_alembic.py tests/test_tasks.py tests/test_checkers.py
cd backend && docstr-coverage --config .docstr.yaml
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 backend/.venv/bin/python scripts/test_agent_gates.py
git diff --check
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78)
cd backend && coverage report --include='app/modules/tasks/*,app/modules/checkers/models.py,app/modules/checkers/repository.py,app/modules/checkers/service.py' --precision=2 --fail-under=90
```

Migration proof also covers prior-head preflight, exact checker-source backfill,
safe downgrade/re-upgrade, protected-row refusal, failed-preflight rollback/no
partial DDL, direct SQL, crossed task/predecessor/run facts, duplicate source,
source immutability, both concurrency orders, and a single head on real
PostgreSQL.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
reuse/dedup, docs, test-delta, and CI integrity.

## Human review focus

Ambiguous historical attribution, human-only identity parity, finalized-row
boundary, concurrent version allocation, ART set-once compatibility, and
downgrade refusal.

## Stop conditions

- Stop if the AUTH foundation is incomplete or a retired contributor-identity
  storage name remains.
- Stop if attribution or guide context cannot be proved for every migrated row.
- Merge, record automated memory, and stop. Do not start 03A automatically.
