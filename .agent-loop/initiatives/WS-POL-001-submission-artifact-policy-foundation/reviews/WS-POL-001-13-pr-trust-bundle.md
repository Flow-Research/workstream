# PR Trust Bundle: WS-POL-001-13

## Intent

Expose task context and submission requirements through authorized HTTP APIs so workers and operators no longer need to infer locked requirements from failures or inspect Postgres during the next live drill.

## Scope

Implemented APIs 8-10 only:

- `GET /api/v1/tasks/{task_id}/work-context`
- `GET /api/v1/tasks/{task_id}/submission-requirements`
- `GET /api/v1/tasks/{task_id}/locked-context`

## Design

Task context APIs read the task's already-stamped locked context. They do not recompute from the current active guide or current project policy.

Worker-facing APIs return:

- safe task summary
- project and locked guide summary
- stamped payment terms
- review/revision guide-version references
- lifecycle next actions
- exact submission packet fields, including `package_hash`
- artifact, evidence, storage, packaging, hash, and attestation requirements

Operator-only `locked-context` returns full locked provenance for `admin` and `project_manager`.

The implementation also redacts existing worker-visible task reads so `GET /tasks/{task_id}` cannot bypass the worker-safe projection.

## Authorization

- `work-context`: existing task visibility for `admin`, `project_manager`, or eligible/assigned worker.
- `submission-requirements`: existing task visibility for `admin`, `project_manager`, or eligible/assigned worker.
- `locked-context`: `admin` or `project_manager` only.
- Persisted actor profiles do not grant route authorization; token-derived roles remain the route gate.

## Evidence

Commands passed:

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
cd backend && .venv/bin/pytest tests/test_tasks.py::test_worker_task_response_redacts_locked_policy_hashes tests/test_tasks.py::test_assigned_worker_submits_v1_and_task_moves_to_submitted tests/test_tasks.py::test_task_context_apis_return_worker_requirements_and_operator_provenance tests/test_tasks.py::test_submission_requirements_fail_closed_on_hash_consistent_malformed_policy_shape -q
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py
cd backend && .venv/bin/pytest tests/test_tasks.py
```

Key results:

- Focused task-context and worker-redaction regressions: 4 passed.
- API contract real API E2E: passed with the three new task-context endpoints.
- Full task suite: 81 passed in 743.67s.
- Stale wording and Markdown links: passed.

## Internal Review

Internal review evidence:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-13-internal-review-evidence.md`

Reviewed code SHA: `449b68093fb62d54a64adab32517cca33f17cb59`

| Reviewer | Result | Blocking findings |
|---|---:|---|
| senior engineering | PASS | None |
| QA/test | PASS | None |
| security/auth | PASS WITH LOW RISKS | None |
| product/ops | PASS | None |
| architecture | PASS | None |
| docs | PASS | None |
| reuse/dedup | PASS WITH LOW RISKS | None |
| test delta | PASS WITH LOW RISKS | None |

All sub-agent sessions were closed.

## External Review

External review has not run yet. CodeRabbit and GitHub checks should review this PR after it is opened.

## Human Review Focus

- Confirm worker-facing requirements are complete enough to submit without exposing internal checker authority.
- Confirm existing `GET /tasks/{task_id}` redaction is acceptable for workers.
- Confirm `locked-context` exposes the right operator provenance and remains restricted to `admin` and `project_manager`.
- Confirm `task_locked_context_invalid` is the right public error code for missing/stale/malformed task locked context.

## Remaining Risks

- Worker-facing locked-context errors include internal field names, but no values, hashes, source refs, bundles, or configs.
- Required packet field constants mirror `SubmissionCreate` and should be kept in sync until a shared schema-derived helper is extracted.
- Full no-DB Terminal Benchmark proof remains assigned to `WS-POL-001-14`.

## Human Merge Ownership

Only the user can approve and merge this PR. Codex must not merge it without explicit user approval for that specific PR.
