# Chunk Contract: WS-POL-001-07 - Task Contract Artifact Field Cleanup

## Parent Initiative

WS-POL-001 - Submission Artifact Policy Foundation

## Goal

Remove the remaining task-owned artifact requirement fields from the current
backend task contract.

`required_files` and `required_evidence` belong to `SubmissionArtifactPolicy`
and the compiled project `PreSubmitCheckerPolicy`. They must not be accepted on
task creation, returned as task fields, or persisted on `workstream_tasks`.

## Why This Chunk Exists

Chunk 3 moved task readiness and submission creation onto the locked project
guide-source snapshot, effective project submission artifact policy, and
project pre-submit checker bundle.

Chunk 6 removed stale project guide and project payment construction-state
fields before the Terminal Benchmark drill continued. The next stale boundary
is task creation: the API still accepts task-level `required_files` and
`required_evidence`, even though those fields no longer define submission
intake. Keeping them makes live API drills look fake because a task creator can
appear to provide the same policy that Workstream should derive and approve at
project scope.

## Risk Class

L1

## SLA

P1

## Implementation Allowed Files

```text
backend/alembic/versions/**
backend/app/modules/tasks/**
backend/tests/test_tasks.py
backend/tests/test_alembic.py
backend/scripts/week1_dry_run.py
backend/scripts/week2_api_e2e.py
docs/architecture_data_model.md
docs/operations_project_operating_manual.md
docs/operations_queue_policy.md
docs/product_first_user_flows.md
docs/spec_chunk_4_task_queue_assignment.md
docs/spec_chunk_8_submission_artifact_policy_checkers.md
docs/template_task.md
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

## Implementation Not Allowed

```text
backend/app/modules/projects/**
backend/app/modules/checkers/**
backend/app/modules/submissions/**
examples/terminal_benchmark/**
demos/**
frontend/**
.github/workflows/**
human review implementation
payment/reputation/blockchain code
project-agent runtime redesign
new checker derivation or compilation per task
```

## Implementation Boundaries

- Task creation remains for task identity, source, description, difficulty,
  skills, timing, acceptance criteria, rejection criteria, and deadline.
- Task creation must reject unknown or stale artifact-policy fields through
  Pydantic `extra="forbid"`.
- Submission artifact requirements remain valid only inside
  `SubmissionArtifactPolicy` / `EffectiveProjectSubmissionArtifactPolicy`.
- The project `PreSubmitCheckerPolicy` remains the runtime pre-submit authority.
- This chunk must not change product project guide setup, policy derivation,
  checker compilation, or Terminal Benchmark example runtime behavior. Helper
  scripts may remove stale project/guide request fields only when needed to keep
  their task-creation drill aligned with the already-merged current API
  contract.
- There is no backward-compatibility alias for task-owned `required_files` or
  `required_evidence`; Workstream is still in build phase and stale contracts
  should be removed.

## Acceptance Criteria

- [ ] `TaskCreate` no longer exposes `required_files` or `required_evidence`.
- [ ] `TaskResponse` no longer exposes `required_files` or `required_evidence`.
- [ ] `WorkstreamTask` no longer maps `required_files` or `required_evidence`.
- [ ] Alembic removes `workstream_tasks.required_files` and
      `workstream_tasks.required_evidence`.
- [ ] Task creation with either stale field returns 422 instead of silently
      accepting the values.
- [ ] Existing task lifecycle and submission tests still prove that pre-submit
      required artifact/evidence checks come from the locked project policy.
- [ ] Real API helper scripts create tasks using the current task request body.
- [ ] Docs/templates no longer describe task-owned artifact requirement fields.

## Verification Commands

```bash
git diff --check
python3 scripts/check_stale_workstream_wording.py
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && .venv/bin/python -m pytest tests/test_tasks.py tests/test_alembic.py
cd backend && .venv/bin/docstr-coverage app scripts --config .docstr.yaml
python3 scripts/check_markdown_links.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
```

## Required Reviewers

Every listed reviewer must end with one exact result value:

- `PASS`
- `PASS AFTER FIXES`
- `PASS WITH LOW RISKS`
- `N/A - with approved reason`

Required:

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- docs
- reuse/dedup
- test delta
- CI integrity

## Human Review Focus

- Task creation no longer accepts stale artifact-policy fields.
- Required artifact/evidence checks remain project-policy driven.
- Migration removes the stale columns without introducing compatibility aliases.
- Real API scripts now reflect the same contract the live Terminal Benchmark
  drill will use.
