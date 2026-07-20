# Chunk Contract: WS-REV-001-02A4 - Task Guide Triplet And Screening

## Goal

Stamp one immutable same-Project guide ID/version/activation-sequence triplet on
each Task when it leaves draft, and make screening compose with guide activation
through the merged Project-first fence.

## Risk Class

L1 schema, migration, task lifecycle concurrency, and audit atomicity.

## Preconditions

- `WS-REV-001-02A3` is merged with valid Project Guide chronology and
  `uq_project_guides_context_triplet`.
- The user separately starts this child. The start refresh records the sole
  Alembic head and allocates only its then-current next revision.

## Database Contract

`WorkstreamTask` adds:

```text
locked_guide_id VARCHAR(36) NULL
locked_guide_activation_sequence BIGINT NULL
```

The migration replaces legacy `fk_workstream_tasks_locked_guide` with:

```text
fk_workstream_tasks_locked_guide_context
  (project_id, locked_guide_id, locked_guide_version,
   locked_guide_activation_sequence)
  -> project_guides(project_id, id, version, activation_sequence)

ck_workstream_tasks_locked_guide_triplet
guard_workstream_task_guide_context()
workstream_tasks_guide_context_guard
```

Draft Tasks require all three guide fields null. Every non-draft Task requires
all three present. The trigger permits the single draft-to-complete allocation
and rejects every later change or clearing of any triplet member.

## Migration Contract

- Lock `project_guides` and `workstream_tasks` before preflight and DDL.
- Reject a draft Task with any legacy locked guide field, a non-draft Task with
  missing guide version, or a non-draft Task whose same-Project version resolves
  to zero/multiple guides or a guide without valid chronology.
- Backfill each valid non-draft Task only from its exact same-Project
  `locked_guide_version`; never choose the currently active/latest guide.
- Bound diagnostics by failure class and row count. Refusal leaves the prior
  revision, data, legacy FK, and complete absence of new objects unchanged.
- Downgrade locks the same tables and refuses before DDL whenever a protected
  Task triplet exists or a later dependency references the new FK/columns. Safe
  downgrade is limited to databases with no allocated Task triplet; it removes
  this chunk's trigger/function/check/FK/columns and restores the legacy FK.
  No automatic clearing or destructive data rewrite occurs.

## Screening Command Order

```text
coarse project operator role check
-> unlocked Task id/project-id projection only
-> Project FOR UPDATE
-> WorkstreamTask FOR UPDATE with populate_existing
-> revalidate task project and draft status
-> selected active ProjectGuide FOR UPDATE with populate_existing
-> load/revalidate exact setup graph under the Project fence
-> stamp guide id/version/activation sequence and existing policy context
-> append audit containing the complete triplet
-> commit once
```

The initial projection grants no authority and is discarded after the locks.
Activation and screening both serialize on Project. No external I/O occurs in
the transaction.

## Allowed Files

```text
backend/app/modules/projects/repository.py only for the locked active-guide read
backend/app/modules/tasks/{models,schemas,repository,service}.py
backend/app/db/models.py
backend/alembic/versions/<then-current-next>_task_guide_triplet.py
backend/tests/test_{alembic,projects,tasks}.py
.github/workflows/backend.yml only for additive/preserved coverage proof
docs/architecture_data_model.md
docs/architecture_lifecycle_state_machine.md
docs/spec_chunk_3_project_guide_foundation.md
docs/operations_operator_workflow.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-02A4.json
```

## Not Allowed

```text
Project Guide chronology, approval, activation, or setup-writer behavior
Submission attribution, guide stamps, lineage, or immutability
Task or TaskAssignment lifecycle state additions or transition changes
ReviewPolicy, RevisionPolicy, compensation-policy, ART, CON, or AUTH behavior
review queue, Review, finding, FinalAcceptance, or adjudication behavior
```

## Acceptance Criteria

- New draft Tasks expose/store a null triplet. Screening stamps the exact active
  guide triplet atomically with all existing locked context.
- Task, operator locked-context, and contributor work-context schemas expose the
  appropriate exact identity/sequence without leaking internal hashes. Guide
  response exposure is inherited unchanged from merged 02A3. Required-field
  validation includes all Task triplet members.
- Loading locked context validates the Task triplet against one same-Project
  Project Guide rather than resolving by version alone.
- Screening audit contains `locked_guide_id`, `locked_guide_version`, and
  `locked_guide_activation_sequence`. Forced audit failure rolls back status,
  triplet, policies, and payment stamps.
- Direct SQL rejects partial, cross-Project, mixed-guide, nonpositive, changed,
  or cleared triplets.
- Independent-session activation/screening tests observe PostgreSQL lock waits
  and both commit orders: screening-first stamps the old active guide fully;
  activation-first stamps the new active guide fully; no mixed or inactive-at-
  selection context commits.
- Existing checker-caused revision, task transitions, submission creation, and
  role/visibility behavior remain unchanged.
- Real-PostgreSQL tests prove upgrade/backfill/refusal, safe downgrade/
  re-upgrade, protected-row refusal, direct SQL, rollback, and one head.
- Existing task 90 percent and global 78 percent gates remain mandatory. If the
  allowed project repository file changes, the project 90 percent report is
  mandatory.

## Verification

```bash
(cd backend && .venv/bin/alembic heads)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q tests/test_alembic.py tests/test_projects.py tests/test_tasks.py)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78)
(cd backend && .venv/bin/coverage report --include='app/modules/tasks/*' --precision=2 --fail-under=90)
(cd backend && .venv/bin/coverage report --include='app/modules/projects/*' --precision=2 --fail-under=90) # mandatory when the allowed project repository file changes
(cd backend && .venv/bin/python -m ruff check app/modules/projects/repository.py app/modules/tasks app/db/models.py alembic/versions tests/test_alembic.py tests/test_projects.py tests/test_tasks.py)
(cd backend && .venv/bin/docstr-coverage --config .docstr.yaml)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_review_contracts.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_internal_review_evidence.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 backend/.venv/bin/python scripts/test_agent_gates.py
backend/.venv/bin/python scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
git diff --unified=0 origin/main...HEAD -- backend/tests | (! rg '^-(.*assert|.*pytest\.raises|.*pytest\.mark\.(skip|xfail)|.*skipTest)')
git diff --check
```

## Required Reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human Review Focus

Legacy backfill refusal, exact composite FK, set-once trigger, unlocked
projection safety, identity-map refresh, audit rollback, activation/screening
races, response visibility, and unchanged task lifecycle.

## Stop Condition

Stop if guide chronology is incomplete, historical Task context is ambiguous,
or a Submission field must change. Merge, record automated memory, and stop. Do
not start 02B automatically.
