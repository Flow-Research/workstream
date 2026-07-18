# Chunk Contract: WS-REV-001-02C - Submission Attribution, Context, And Immutable Lineage

## Parent initiative

`WS-REV-001` - Review And Revision Lifecycle

## Goal

Bind every existing versioned Submission to the exact TaskAssignment and
canonical contributor that produced it, stamp the complete guide identity, and
enforce immutable immediate-predecessor lineage after finalization.

## Why this chunk exists

Current Submission service logic allocates sequential versions, but direct SQL
can create cross-task or skipped predecessor chains and prior attribution can be
misread after reassignment. The existing Submission must become durable review
lineage without introducing a competing SubmissionVersion table.

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
backend/app/db/models.py
backend/alembic/versions/<then-current-next>_submission_attribution_lineage.py
backend/tests/test_{alembic,tasks}.py
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
ProjectGuide activation allocation or ReviewPolicy shape
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
- Draft/staged submission fields required by current finalization/checker flows
  remain mutable only until the existing finalization boundary. After physical
  `Submission.locked_at` is set (publicly serialized as `finalized_at`),
  identity, task/assignment/contributor, version,
  predecessor, locked context, packet, evidence, and attestation fields are
  update/delete protected. Later ART-owned server-derived `artifact_hash`
  publication remains an explicitly allowed set-once extension and is not
  implemented here.
- Version allocation and predecessor selection lock the Task plus current chain
  head so concurrent submissions cannot allocate the same version or create two
  successors.
- TaskAssignment continues to store only task identity and contributor/freeze
  terms; it receives no guide or revision-preparation duplicate.
- Submission creation revalidates that the canonical contributor ActorProfile
  is active in the transaction through the supported AUTH-owned boundary.
  Suspended/deactivated humans, services, external subjects, emails, legacy
  profile IDs, and token-role values cannot substitute.
- No Review, queue entry, checker decision, contribution, or task terminal
  effect is created by migration or lineage enforcement.
- Downgrade refuses after rows depend on the new assignment/guide lineage unless
  the documented destructive remediation procedure is used.

## Verification commands

```text
cd backend && alembic upgrade head
cd backend && pytest -q tests/test_alembic.py tests/test_tasks.py
cd backend && ruff check app/modules/tasks tests/test_alembic.py tests/test_tasks.py
cd backend && docstr-coverage --config .docstr.yaml
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
```

The full isolated PostgreSQL suite must preserve the repository-wide 78 percent
floor. Every materially changed tasks module must remain at or above 90 percent
coverage.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
reuse/dedup, docs, and test-delta.

## Human review focus

Ambiguous historical attribution, human-only identity parity, finalized-row
boundary, concurrent version allocation, ART set-once compatibility, and
downgrade refusal.

## Stop conditions

- Stop if the AUTH foundation is incomplete or a retired contributor-identity
  storage name remains.
- Stop if attribution or guide context cannot be proved for every migrated row.
- Merge, record automated memory, and stop. Do not start 03 automatically.
