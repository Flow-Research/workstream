# PR Trust Bundle: WS-POL-001-07

## Chunk

`WS-POL-001-07` - Task Contract Artifact Field Cleanup

## Goal

Remove the remaining task-owned artifact requirement fields from the current
backend task contract.

`required_files` and `required_evidence` now belong only to
`SubmissionArtifactPolicy`, `EffectiveProjectSubmissionArtifactPolicy`, and the
compiled project `PreSubmitCheckerPolicy`. Task creation describes the work; it
does not author submission artifact policy.

## Human-Approved Intent

The user explicitly pushed back that:

- request bodies must hard-fail fields that no longer belong there;
- no backward-compatibility alias is needed while Workstream is still in build
  phase;
- project owners provide project material and business terms, but Workstream
  derives and approves internal artifact-intake policy;
- tasks must not fake project policy by accepting `required_files` or
  `required_evidence`;
- the next Terminal Benchmark drill should use real current APIs one step at a
  time.

## What Changed

- Added `0011_remove_legacy_task_artifact_fields.py`.
- Dropped `workstream_tasks.required_files` and
  `workstream_tasks.required_evidence`.
- Removed both fields from `WorkstreamTask`, `TaskCreate`, `TaskResponse`, and
  task creation service assignment.
- Added API coverage proving task creation with stale artifact requirement
  fields returns 422.
- Added Alembic coverage proving the removed task columns are absent at
  migration head.
- Updated Week 1/Week 2 helper scripts so task creation uses the current task
  request body.
- Removed stale project-shell payment fields from the Week 2 helper script.
- Removed stale project/guide request fields from `week1_dry_run.py` so the
  helper stays aligned with the current API.
- Updated active docs and templates so task records describe source, work,
  acceptance, rejection, and locked policy snapshots, while machine-enforced
  artifact and evidence rules are project-policy owned.
- Updated WS-POL status/chunk map/loop state for Chunk 7.

## Design Chosen

Current authority is:

```text
ProjectGuide = human-facing project material
SubmissionArtifactPolicy = Workstream-derived artifact-intake contract
EffectiveProjectSubmissionArtifactPolicy = default + project policy merge
Project PreSubmitCheckerPolicy = deterministic compiled checker bundle
Task = locks the active project policy/checker context
```

Task fields can describe source, title, description, difficulty, skill tags,
estimated time, acceptance criteria, rejection criteria, and deadline. They do
not define required artifacts, evidence, hashes, packaging, or forbidden
artifacts.

## Scope

Runtime/backend:

- `backend/alembic/versions/0011_remove_legacy_task_artifact_fields.py`
- `backend/app/modules/tasks/models.py`
- `backend/app/modules/tasks/schemas.py`
- `backend/app/modules/tasks/service.py`

Tests/scripts:

- `backend/tests/test_alembic.py`
- `backend/tests/test_tasks.py`
- `backend/scripts/week1_dry_run.py`
- `backend/scripts/week2_api_e2e.py`

Docs/process:

- `.agent-loop/LOOP_STATE.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**`
- `docs/architecture_data_model.md`
- `docs/operations_project_operating_manual.md`
- `docs/operations_queue_policy.md`
- `docs/product_first_user_flows.md`
- `docs/spec_chunk_4_task_queue_assignment.md`
- `docs/spec_chunk_8_submission_artifact_policy_checkers.md`
- `docs/template_task.md`

## Product Behavior

- Task create rejects `required_files` and `required_evidence` through
  `extra="forbid"`.
- Task responses no longer show stale artifact requirement snapshots.
- Tasks still lock guide/source/effective-policy/pre-submit-checker context
  before entering the worker pipeline.
- Pre-submit required artifact/evidence checks continue to come from the locked
  project policy and project `PreSubmitCheckerPolicy`.
- Payment values on tasks remain locked snapshots from `PaymentPolicy`.

## Verification

Passed locally:

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_tasks.py tests/test_alembic.py
git diff --check
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
cd backend && .venv/bin/docstr-coverage app scripts --config .docstr.yaml
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests
```

Results:

- ruff: passed
- focused task/Alembic suite: 67 passed
- stale wording scan: passed
- Markdown link check: passed
- docstring coverage: 100.0%
- full backend suite: 330 passed

Post-review repair verification:

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_alembic.py tests/test_tasks.py
```

Results:

- ruff: passed
- stale wording scan: passed
- Markdown link check: passed
- diff whitespace check: passed
- focused task/Alembic suite: 67 passed

## Internal Review

Evidence:

`.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-07-internal-review-evidence.md`

Reviewed implementation SHA:

`4845f9891362caad479030d339e512dbe5924b46`

Reviewer summary:

- senior engineering: PASS AFTER FIXES
- QA/test: PASS AFTER FIXES
- security/auth: PASS
- product/ops: PASS AFTER FIXES
- architecture: PASS
- docs: PASS AFTER FIXES
- reuse/dedup: PASS
- test delta: PASS
- CI integrity: PASS AFTER FIXES

## External Review

GitHub Actions passed on PR #68. CodeRabbit posted two actionable documentation
comments, both addressed in:

`.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-07-external-review-response.md`

## Remaining Risks

- The full backend suite passed before the final direct Alembic assertion and
  helper-script cleanup. The post-fix focused task/Alembic suite and ruff/docs
  checks passed after those repairs.
- Historical review evidence still mentions old construction-state fields
  because it records earlier chunks; active docs and runtime contracts now use
  the project-policy authority model.

## Human Review Focus

- Confirm task creation should no longer accept artifact requirement fields.
- Confirm there is no compatibility alias for `required_files` /
  `required_evidence` on tasks.
- Confirm required artifact/evidence checks remain project-policy driven.
- Confirm the helper-script cleanup is acceptable as request-body alignment for
  live drills, not a product setup redesign.
