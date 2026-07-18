# Internal Review Evidence: WS-POL-001-07

## Chunk

WS-POL-001-07

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 4845f9891362caad479030d339e512dbe5924b46

Reviewed at: 2026-07-05T16:49:33Z

Reviewer run IDs: 019f32de-d755-7a11-aa0b-8c6fd43251c8, 019f32de-dfed-7510-9ede-44798d7fa35a, 019f32de-e9bb-7711-b976-cbde1f21d971, 019f32de-f304-7a01-bcf8-f589db625af7, 019f32de-ffff-7a21-8242-ce9154dfd660, 019f32df-4c04-7c90-9225-4630ca51ef1d, 019f3301-a155-7391-a160-9a6cf52bc6d3, 019f3301-ae4f-7e02-bb48-82d90e5c11fc, 019f3301-b9af-7c82-a753-69660c9519ab, 019f3301-c21b-7b21-832e-14b89807ffcb, 019f3301-c824-7fa2-b9e5-416e2cdb8183, 019f3301-ccf8-7a73-8bc1-c55743514284, 019f331a-c54e-7691-8222-bedc15db01d6, 019f331a-ca63-7cd1-9eff-74c35fe29c1c, 019f331d-e7e0-7161-a9d2-3bacf81b2c04, 019f331d-ec0c-7201-92eb-6716b23e4f7f, 019f332c-bd4c-7e31-be43-7bf4c150622f, 019f332c-c2e2-7d72-8718-8219d59c9d1f, 019f332c-c7ab-78f1-8419-9eecc882c154, 019f332c-cedf-7212-a528-50858e2f515a

## Reviewed Change

Branch: `codex/ws-pol-001-07-task-contract-cleanup`

Scope:

- `.agent-loop/LOOP_STATE.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**`
- `backend/alembic/versions/0011_remove_legacy_task_artifact_fields.py`
- `backend/app/modules/tasks/models.py`
- `backend/app/modules/tasks/schemas.py`
- `backend/app/modules/tasks/service.py`
- `backend/scripts/week1_dry_run.py`
- `backend/scripts/week2_api_e2e.py`
- `backend/tests/test_alembic.py`
- `backend/tests/test_tasks.py`
- `docs/architecture_data_model.md`
- `docs/operations_project_operating_manual.md`
- `docs/operations_queue_policy.md`
- `docs/product_first_user_flows.md`
- `docs/spec_chunk_4_task_queue_assignment.md`
- `docs/spec_chunk_8_submission_artifact_policy_checkers.md`
- `docs/template_task.md`

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Initial pass found dirty-worktree review, missing direct Alembic assertion, and an unclear helper-script exception. Commit `55cc79a0` fixed those and the rerun found no remaining issues. |
| qa/test | PASS AFTER FIXES | None | Initial pass found the untracked migration and missing direct schema assertion. Commit `55cc79a0` tracks the migration and asserts removed task columns are absent after `head`. |
| security/auth | PASS | None | Confirmed stale client-supplied artifact policy fields are rejected, no policy-context spoofing was introduced, and the cleanup does not weaken auth or data boundaries. |
| product/ops | PASS AFTER FIXES | None | Found stale project-shell payment fields in `week2_api_e2e.py`; commit `55cc79a0` removed them. Later evidence-missing process finding is addressed by this file. |
| architecture | PASS | None | Confirmed artifact requirements remain project-policy authority and tasks do not own `required_files` / `required_evidence`. |
| docs | PASS AFTER FIXES | None | Confirmed active docs/templates point artifact requirements to project policy authority. Later CodeRabbit docs comments were fixed at `4845f989` and the stale-evidence finding is addressed by this refresh. |
| reuse/dedup | PASS | None | Confirmed no duplicate artifact-requirement path or missed shared helper was introduced. |
| test delta | PASS | None | Confirmed tests were not weakened; task stale-field rejection and direct migration assertions were added. |
| ci integrity | PASS AFTER FIXES | None | Found missing internal-review evidence before this file existed. This evidence file, status update, and rerun close that process finding. |

## Valid Findings Addressed

- Tracked `backend/alembic/versions/0011_remove_legacy_task_artifact_fields.py`
  so the migration is part of the branch and PR diff.
- Added direct Alembic assertions that `workstream_tasks.required_files` and
  `workstream_tasks.required_evidence` are absent after upgrading to `head`.
- Removed task-owned `required_files` and `required_evidence` from `TaskCreate`,
  `TaskResponse`, `WorkstreamTask`, and task creation service code.
- Added task API coverage proving stale artifact requirement fields now return
  422 instead of being accepted.
- Preserved required artifact/evidence runtime behavior through the locked
  project `PreSubmitCheckerPolicy` and effective project submission artifact
  policy.
- Removed stale task artifact fields from Week 1/Week 2 helper task payloads.
- Removed stale project-shell payment fields from the Week 2 helper project
  payload; payment terms remain in `PaymentPolicy`.
- Removed stale project/guide request fields from `week1_dry_run.py` so that
  helper script remains aligned with the already-merged current project API
  contract.
- Clarified the chunk contract to allow helper-script request-body cleanup while
  keeping product project guide setup out of scope.
- Updated active docs and task template wording so task records describe work,
  source, acceptance, and rejection, while machine-enforced artifact and
  evidence requirements stay under project policy.
- Addressed CodeRabbit docs feedback by clarifying that `check_required_files`
  reads required artifact paths from `context.effective_policy`.
- Updated the task template stamped submission artifact policy context to use
  backend-aligned locked guide-source, effective-policy, and pre-submit-checker
  id/hash labels.

## Verification

Passed locally before reviewer fanout:

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
- `tests/test_tasks.py tests/test_alembic.py`: 67 passed in 0:11:01
- stale wording scan: passed
- Markdown link check: passed for 11 changed Markdown files
- docstring coverage: 100.0%
- full backend suite: 330 passed in 0:43:00

Post-fix verification after reviewer findings:

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
- Markdown link check: passed for 11 changed Markdown files
- diff whitespace check: passed
- `tests/test_alembic.py tests/test_tasks.py`: 67 passed in 0:11:28

## External Review Status

External GitHub Actions and CodeRabbit have not run for this branch yet. They
must run after the PR is opened. This internal evidence does not replace
external review.
