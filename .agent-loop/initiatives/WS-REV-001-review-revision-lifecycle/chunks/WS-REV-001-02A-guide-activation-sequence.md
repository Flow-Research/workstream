# Chunk Contract: WS-REV-001-02A - Project Guide Activation Sequence And Publication Locking

## Parent initiative

`WS-REV-001` - Review And Revision Lifecycle

## Goal

Give every activated Project Guide an immutable per-project chronology and make
guide publication assemble and lock one internally consistent generation.

## Why this chunk exists

Revision rebase compares the prior Submission's stamped guide identity with the
currently active guide. Semantic or lexical version comparison cannot establish
chronology, and the current activation path can read policy rows from mixed
generations. This child establishes the chronology and Task-side lock before
Submission copies it in 02C.

## Risk class

L1 schema, migration, and concurrency.

## SLA

P2.

## Preconditions

- AUTH-09D-A and the separately reviewed AUTH-owned contributor-field
  foundation are merged, even though this child does not edit contributor
  fields; the user has declared that foundation a runtime gate for all REV-02
  implementation.
- Dependency refresh records exact merged PR/SHA evidence and the then-current
  single Alembic head. REV does not reserve a migration number during planning.
- This contract receives a separate human start after parent 02 planning is
  approved.

## Allowed files

```text
backend/app/modules/projects/{models,schemas,repository,service}.py
backend/app/modules/tasks/{models,schemas,repository,service}.py only for Task guide stamps
backend/app/db/models.py
backend/alembic/versions/<then-current-next>_guide_activation_sequence.py
backend/tests/test_{alembic,projects,tasks}.py
docs/architecture_data_model.md
docs/architecture_lifecycle_state_machine.md
docs/operations_operator_workflow.md only for migration/deployment/remediation
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-02A.json
```

## Not allowed changes

```text
Submission attribution, lineage, or immutability
ReviewPolicy or RevisionPolicy field changes
Task or TaskAssignment lifecycle state changes
AUTH-owned contributor or ActorProfile schema
review queue, lease, Review, finding, FinalAcceptance, or public review routes
ART, CON, compensation, contribution, adjudication, or synthetic reject behavior
```

## Acceptance criteria

- `ProjectGuide.activation_sequence` is a nullable positive bigint allocated
  exactly once on first activation.
- Database checks require drafts to have null sequence and active/superseded
  guides to have a non-null sequence; `(project_id, activation_sequence)` is
  unique.
- A database guard rejects sequence mutation or clearing. Reactivating a
  previously activated guide preserves its original sequence and allocates no
  second value.
- Existing active/superseded guides are deterministically numbered per project
  by `effective_at`, `created_at`, then `id`. Missing required activation
  provenance, invalid status/sequence shape, or conflicting historical data
  fails with an actionable remediation message. Drafts remain null.
- Activation takes a `FOR UPDATE` project row lock before allocating
  `max(activation_sequence)+1`; concurrent first activations cannot duplicate or
  invert allocation.
- Publication uses this exact lock order: Project; candidate/current
  ProjectGuide rows; GuideSourceSnapshot; GuideSufficiencyReport;
  ProjectSetupRun; SubmissionArtifactPolicy;
  EffectiveProjectSubmissionArtifactPolicy; PreSubmitCheckerPolicy;
  PostSubmitCheckerPolicy; ReviewPolicy; RevisionPolicy; then the transitional
  compensation-context row if it still exists. Rows of one type lock by ascending
  primary key. That retired row is consistency input only and is not copied into
  the final guide/revision context.
- `WorkstreamTask` stamps `locked_guide_id`, `locked_guide_version`, and
  `locked_guide_activation_sequence` as one composite guide identity when it
  leaves draft. Draft tasks keep the triplet null; non-draft tasks require it
  complete and reference one guide row.
- Existing non-draft tasks backfill only from an exact same-project locked
  guide version with a valid activation sequence. Missing or ambiguous context
  fails migration rather than choosing the current guide.
- Publication cannot assemble policy rows from different guide/source/policy
  generations and performs no external I/O while locks are held.
- First activation is allowed only from draft: it allocates sequence, records
  `approved_by` and `effective_at=database_now`, and clears no historical
  provenance. Repeating activation of the sole active candidate is idempotent
  and changes no timestamp, provenance, sequence, or audit row.
- Reactivation is allowed only from superseded. It preserves original
  `approved_by`, `effective_at`, and activation sequence; changes status to
  active; clears `superseded_at`; supersedes the current active guide at
  database time; and appends a reactivation audit event with server-owned reason
  `older_guide_reactivated`, canonical actor, and replaced guide. The existing
  route gains no caller-supplied reason or request body. No other status may
  reactivate.
- Two competing activations/reactivations serialize under the Project lock.
  Each valid request observes and supersedes the then-current guide; both lock
  acquisition orders leave exactly one active guide and preserve every
  previously allocated sequence.
- Downgrade refuses once Task rows stamp activation sequence unless the operator
  uses the documented destructive remediation procedure.

## Verification commands

```text
cd backend && alembic upgrade head
cd backend && pytest -q tests/test_alembic.py tests/test_projects.py tests/test_tasks.py
cd backend && ruff check app/modules/projects app/modules/tasks tests/test_alembic.py tests/test_projects.py tests/test_tasks.py
cd backend && docstr-coverage --config .docstr.yaml
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
```

The full isolated PostgreSQL suite must preserve the repository-wide 78 percent
floor. Every materially changed projects/tasks module must remain at or above
90 percent coverage.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
reuse/dedup, docs, and test-delta.

## Human review focus

Historical ordering, concurrent allocation, reactivation preservation, lock
order, task backfill refusal, and downgrade limits.

## Stop conditions

- Stop if contributor or ActorProfile schema must change.
- Stop if historical task/guide lineage is ambiguous.
- Merge, record automated memory, and stop. Do not start 02B automatically.
