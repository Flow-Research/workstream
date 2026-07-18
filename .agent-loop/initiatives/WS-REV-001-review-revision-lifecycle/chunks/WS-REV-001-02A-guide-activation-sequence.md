# Chunk Contract: WS-REV-001-02A - Project Guide Activation Sequence And Publication Locking

## Goal

Add immutable per-project guide chronology, make publication and task screening
share Project-first locking, and stamp one immutable guide triplet on each Task.
Do not add public superseded-guide reactivation under legacy authorization.

## Risk class

L1 schema, migration, authorization preservation, and concurrency.

## Preconditions

- AUTH-09D-A is merged through PR #148 at
  `99ae4c963e53f317175dcb308b9e47c93ccf19ed`, with migration
  `0026_actor_profile_lifecycle` and database-backed ActorProfile lifecycle
  evidence.
- The separate AUTH-owned contributor/canonical-human foundation has a real
  trusted-main chunk ID and is merged with exact PR/SHA, migration, constraints,
  and regression evidence. An unmerged branch, worktree, proposed migration
  number, or prose handoff does not satisfy this remaining gate.
- Current-main refresh records the single Alembic head. REV allocates only the
  then-current next migration and does not reserve a number in planning.
- The user separately starts this child after `WS-REV-001-PLAN2` merges.

## Allowed files

```text
backend/app/modules/projects/{models,schemas,repository,service,router}.py
backend/app/workers/project_setup.py only if a direct setup writer must adopt the Project-first fence
backend/app/modules/tasks/{models,schemas,repository,service}.py only for Task guide stamps
backend/app/db/models.py
backend/alembic/versions/<then-current-next>_guide_activation_sequence.py
backend/tests/test_{alembic,projects,tasks}.py
.github/workflows/backend.yml only to persist focused 90 percent coverage gates for changed project/task/setup-job modules
docs/architecture_data_model.md
docs/architecture_lifecycle_state_machine.md
docs/spec_chunk_3_project_guide_foundation.md
docs/operations_operator_workflow.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-02A.json
```

## Not allowed

```text
public or hidden superseded-guide reactivation behavior
Submission attribution, lineage, or immutability
ReviewPolicy or RevisionPolicy changes
Task or TaskAssignment lifecycle state changes
AUTH-owned contributor/ActorProfile schema or authorization implementation
review queue, lease, Review, finding, FinalAcceptance, ART, CON, or adjudication behavior
weakening or removal of any CI, coverage, lint, type, migration, or test gate
```

## Acceptance criteria

- `ProjectGuide.activation_sequence` is a nullable positive bigint allocated
  exactly once on first activation. `(project_id, activation_sequence)` is
  unique and a database guard rejects mutation or clearing.
- The exact status domain is `draft`, `active`, and `superseded`. Draft requires
  null sequence/approver/effective/superseded times; active requires positive
  sequence, canonical-human approver, effective time, and null superseded time;
  superseded requires all activation provenance plus superseded time. Unknown or
  inconsistent shapes fail migration and direct SQL.
- Existing active/superseded guides are numbered per project by `effective_at`,
  `created_at`, then `id`. Missing provenance, duplicate ordering facts, invalid
  status, or conflicting history fails with row-specific remediation. Drafts
  remain null.
- Publication locks Project first, then candidate/current ProjectGuide rows,
  GuideSourceSnapshot, GuideSufficiencyReport, ProjectSetupRun,
  SubmissionArtifactPolicy, EffectiveProjectSubmissionArtifactPolicy,
  PreSubmitCheckerPolicy, PostSubmitCheckerPolicy, ReviewPolicy,
  RevisionPolicy, and the exact current `payment_policies` table row if it still
  exists. Same-type rows lock by ascending ID. If CON removes it first, the
  refresh removes that lock rather than adding an alias.
- Every service or setup-job mutation of a guide, source snapshot, sufficiency
  report, setup run, or listed policy row first locks the same Project, then its
  target rows in the publication type/ID order, and revalidates that the guide is
  still draft before writing. Project-setup job entry points call those fenced
  service methods and perform no direct database mutation. This shared prefix is required
  for the claimed activation/setup/screening race safety.
- First activation reads database time after locks, allocates
  `max(activation_sequence)+1`, and records the canonical approver/effective
  time. Concurrent first activations serialize and cannot duplicate or invert
  allocation. Publication performs no external I/O under locks.
- The existing public route continues to allow draft first activation and the
  no-write idempotent repeat of the sole active candidate. A superseded
  candidate remains denied. This chunk does not broaden legacy local role
  authorization or expose backward reactivation.
- `WorkstreamTask` stamps `locked_guide_id`, `locked_guide_version`, and
  `locked_guide_activation_sequence` as one triplet when leaving draft. Draft
  tasks keep all three null; non-draft tasks require all three and one exact
  same-project guide. A database guard rejects every valid-to-valid change or
  clearing after allocation.
- Task screening locks Project first, then Task and the selected active guide
  before context validation/stamping. Activation, setup mutation, setup-worker
  completion, and screening races run with independent sessions in both commit
  orders and cannot produce a mixed or no-longer-active generation stamp.
- Existing non-draft Task backfill uses only an exact same-project locked guide
  version with a valid sequence. Missing/ambiguous context fails rather than
  selecting the current guide.
- Screening audit includes the complete guide triplet. Audit failure rolls back
  Task stamping. One post-lock database timestamp controls each mutation.
- Downgrade refuses after protected guide sequences or Task stamps exist unless
  the documented destructive remediation is performed.
- Backend CI persistently executes the focused 90 percent coverage checks for
  every materially changed project/task/setup-job module; the proof is not only
  a one-time local command. Existing global 78 percent and all other gates remain
  unchanged or stronger.

## Verification

```text
cd backend && alembic heads
cd backend && alembic upgrade head
cd backend && pytest -q tests/test_alembic.py tests/test_projects.py tests/test_tasks.py
cd backend && ruff check app/modules/projects app/modules/tasks app/workers/project_setup.py tests/test_alembic.py tests/test_projects.py tests/test_tasks.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 backend/.venv/bin/python scripts/test_agent_gates.py
git diff --check
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78)
cd backend && coverage report --include='app/modules/projects/*' --precision=2 --fail-under=90
cd backend && coverage report --include='app/modules/tasks/*' --precision=2 --fail-under=90
cd backend && coverage report --include='app/workers/project_setup.py' --precision=2 --fail-under=90
```

Migration proof uses real PostgreSQL and covers prior-head preflight, upgrade,
safe downgrade/re-upgrade, protected-row downgrade refusal, failed-preflight
rollback/no partial DDL, direct-SQL constraints, and a single head. The isolated
full suite preserves the 78 percent floor; every materially changed project/task
module remains at or above 90 percent.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta, and CI integrity if coverage workflow changes.

## Human review focus

Historical ordering, Project-first races, Task triplet immutability, canonical
approver enforcement, unchanged public authorization, and downgrade limits.

## Stop condition

Stop if AUTH contributor/actor schema must change or historical lineage is
ambiguous. Merge, record automated memory, and stop. Do not start 02B.
