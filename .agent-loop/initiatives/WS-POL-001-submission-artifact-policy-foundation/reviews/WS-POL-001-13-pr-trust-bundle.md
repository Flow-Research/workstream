# PR Trust Bundle: WS-POL-001-13

## Chunk

`WS-POL-001-13` - Task context and submission requirement APIs.

## Goal

Expose task context and submission requirements through authorized HTTP APIs so
workers and operators no longer need to infer locked requirements from failures
or inspect Postgres during the next live drill.

## Human-approved intent

Chunk contract:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-13-task-context-submission-requirements-apis.md`

The user approved exposing worker-safe task context, exact submission
requirements, and operator-only locked provenance APIs before rerunning the
Terminal Benchmark drill.

## What changed

Implemented APIs 8-10 only:

- `GET /api/v1/tasks/{task_id}/work-context`
- `GET /api/v1/tasks/{task_id}/submission-requirements`
- `GET /api/v1/tasks/{task_id}/locked-context`

The implementation also redacts existing worker-visible task reads so
`GET /tasks/{task_id}` cannot bypass the worker-safe projection.

## Why it changed

The Terminal Benchmark drill showed that setup and task policy state was still
too dependent on direct database inspection. This chunk exposes the
already-locked task context through authorized APIs while preserving the rule
that runtime uses stamped policy references, not recomputed current project
state.

## Design chosen

Task context APIs read the task's already-stamped locked context. They do not
recompute from the current active guide or current project policy.

Worker-facing APIs return:

- safe task summary
- project and locked guide summary
- stamped payment terms
- review/revision guide-version references
- lifecycle next actions
- exact submission packet fields, including `package_hash`
- artifact, evidence, storage, packaging, hash, and attestation requirements

Operator-only `locked-context` returns full locked provenance for `admin` and
`project_manager`.

Authorization:

- `work-context`: existing task visibility for `admin`, `project_manager`, or
  eligible/assigned worker.
- `submission-requirements`: existing task visibility for `admin`,
  `project_manager`, or eligible/assigned worker.
- `locked-context`: `admin` or `project_manager` only.
- Persisted actor profiles do not grant route authorization; token-derived
  roles remain the route gate.

## Alternatives rejected

- Recomputing task requirements from the current active guide at read time:
  rejected because tasks must expose the stamped context they already locked.
- Exposing compiled bundles, checker configs, source refs, or private policy
  internals to workers: rejected because worker-facing APIs should show what
  must be submitted, not checker authority.
- Continuing to inspect Postgres during the live drill: rejected because the
  next drill must prove the public/operator API surface.

## Scope control

### Allowed files changed

- `backend/app/modules/tasks/router.py`
- `backend/app/modules/tasks/schemas.py`
- `backend/app/modules/tasks/service.py`
- `backend/scripts/api_contract_e2e.py`
- `backend/tests/test_tasks.py`
- `docs/architecture_data_model.md`
- `docs/architecture_system_architecture.md`
- `docs/glossary.md`
- `docs/operations_project_operating_manual.md`
- `docs/roadmap_status.md`
- `.agent-loop/LOOP_STATE.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/STATUS.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-13-internal-review-evidence.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-13-external-review-response.md`
- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-13-pr-trust-bundle.md`

### Files outside scope

None.

## Product Behavior

- [ ] No Workstream product behavior changed.
- [x] Product behavior changed and is explained here:

Workers and operators can now inspect task context and submission requirements
through authorized APIs. Worker responses are intentionally redacted. Operators
with `admin` or `project_manager` can inspect full locked provenance.

## Acceptance criteria proof

- [x] Worker-safe task context API exists and reads locked context.
  Evidence: `test_task_context_apis_return_worker_requirements_and_operator_provenance`.
- [x] Submission requirements API returns exact packet, artifact, evidence,
  storage, packaging, hash, and attestation requirements.
  Evidence: `test_task_context_apis_return_worker_requirements_and_operator_provenance`
  and `scripts/api_contract_e2e.py`.
- [x] Operator locked-context API is restricted to `admin` and
  `project_manager`.
  Evidence: `test_task_context_apis_return_worker_requirements_and_operator_provenance`.
- [x] Missing, stale, or malformed locked context fails closed.
  Evidence: `test_submission_requirements_fail_closed_on_hash_consistent_malformed_policy_shape`.
- [x] Worker-facing task reads remain redacted.
  Evidence: `test_worker_task_response_redacts_locked_policy_hashes`.

## Tests/checks run

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
cd backend && .venv/bin/pytest tests/test_tasks.py::test_worker_task_response_redacts_locked_policy_hashes tests/test_tasks.py::test_assigned_worker_submits_v1_and_task_moves_to_submitted tests/test_tasks.py::test_task_context_apis_return_worker_requirements_and_operator_provenance tests/test_tasks.py::test_submission_requirements_fail_closed_on_hash_consistent_malformed_policy_shape -q
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py
cd backend && .venv/bin/pytest tests/test_tasks.py
cd backend && .venv/bin/pytest tests/test_tasks.py::test_submission_requirements_fail_closed_on_hash_consistent_malformed_policy_shape -q
cd backend && .venv/bin/python -m ruff check tests/test_tasks.py
```

Result summary:

```text
Focused task-context and worker-redaction regressions: 4 passed
API contract real API E2E: passed with the three new task-context endpoints
Full task suite: 81 passed in 743.67s
CodeRabbit regression pytest: 1 passed
Ruff: passed
Stale wording: passed
Markdown links: passed
git diff --check: passed
```

## Test delta

### Tests added

- Added task API coverage for worker-facing work context and submission
  requirements.
- Added operator-only locked-context API coverage.
- Added fail-closed locked-context validation coverage.
- Added regression coverage for worker redaction on existing task reads.
- Extended the real API contract drill to call the three new endpoints.

### Tests modified

- Updated `test_submission_requirements_fail_closed_on_hash_consistent_malformed_policy_shape`
  after CodeRabbit review to capture the compiled bundle before deleting the
  ORM row.

### Tests removed/skipped

None.

## CI integrity

- [x] Coverage threshold unchanged
- [x] Lint unchanged
- [x] Typecheck unchanged
- [x] No workflow weakening
- [x] No package script weakening
- [x] No unpinned new GitHub Action
- [x] Checkout credential persistence unchanged

## External review

External review response file:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-13-external-review-response.md`

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Addressed locally | One valid test-maintainability nitpick and one PR-description warning were fixed. |
| GitHub checks | Pending rerun | Existing checks passed before this external-review response commit; they must rerun after push. |

## Reviewer results

Reviewed implementation SHA: `f533f1a572a38d4e8ecd34ff6316885c6c6b1016`

Reviewed at: 2026-07-08T02:09:55Z

Reviewer run IDs:

- senior engineering: `019f3f6d-441f-7340-9bcc-ef92155d956d`
- QA/test: `019f3f6d-4986-7612-a7a7-9457a2182d0b`
- security/auth: `019f3f6d-4fea-7890-a372-a261d2482b91`
- product/ops: `019f3f6d-5758-79d3-a7d4-3d58933064da`
- docs: `019f3f6d-6062-7590-8358-3bc0766e935d`
- reuse/dedup: original internal review evidence
- test delta: `019f3f6d-685a-7300-82ab-966c3c034976`

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Confirmed the CodeRabbit test fix is minimal. |
| QA/test | PASS WITH LOW RISKS | None | Confirmed coverage is not weakened. |
| security/auth | PASS | None | Confirmed no auth or data-leakage risk in the delta. |
| product/ops | PASS | None | Confirmed external review stays separate from internal evidence and human merge ownership remains intact. |
| architecture | PASS | None | Original internal review result. |
| CI integrity | N/A - with approved reason | None | No CI/workflow/package-script files changed in the external-review response delta. |
| docs | PASS AFTER FIXES | None | Initial template-format finding was fixed. |
| reuse/dedup | PASS WITH LOW RISKS | None | Original internal review result. |
| test delta | PASS | None | Confirmed the test still proves fail-closed malformed policy behavior. |

All sub-agent sessions were closed before final reporting.

## Remaining risks

- Worker-facing locked-context errors include internal field names, but no
  values, hashes, source refs, bundles, or configs.
- Required packet field constants mirror `SubmissionCreate` and should be kept
  in sync until a shared schema-derived helper is extracted.
- Full no-DB Terminal Benchmark proof remains assigned to `WS-POL-001-14`.

## Follow-up work

- `WS-POL-001-14`: replace public submission lock wording with finalize,
  define system actor audit semantics, and rerun the Terminal Benchmark proof
  without DB inspection.
- Later cleanup: extract a shared schema-derived helper for required packet
  fields if another caller needs the same constants.

## Human review focus

Please inspect:

- Confirm worker-facing requirements are complete enough to submit without
  exposing internal checker authority.
- Confirm existing `GET /tasks/{task_id}` redaction is acceptable for workers.
- Confirm `locked-context` exposes the right operator provenance and remains
  restricted to `admin` and `project_manager`.
- Confirm `task_locked_context_invalid` is the right public error code for
  missing/stale/malformed task locked context.

## Human ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
