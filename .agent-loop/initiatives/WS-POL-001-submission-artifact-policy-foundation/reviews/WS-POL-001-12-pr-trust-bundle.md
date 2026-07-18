# PR Trust Bundle: WS-POL-001-12

## Intent

Expose project setup and project policy state through authorized HTTP APIs so a real operator drill does not need to inspect Postgres to find setup outputs.

## Scope

Implemented APIs 1-7 only:

- `GET /api/v1/projects/{project_id}/guides/{guide_id}/setup-runs/latest`
- `GET /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports`
- `GET /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}`
- `GET /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies`
- `GET /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}`
- `GET /api/v1/projects/{project_id}/guides/{guide_id}/effective-submission-artifact-policy`
- `GET /api/v1/projects/{project_id}/guides/{guide_id}/pre-submit-checker-policy`

## Design

`ProjectSetupRun` is a non-authoritative orchestration ledger. It records setup execution, queue status, worker status, Celery task id, safe error summary, and output ids. It does not replace guide source snapshots, sufficiency reports, submission artifact policies, effective project policies, or compiled pre-submit checker policies as truth.

The worker validates that its task payload matches the setup-run row and validates output ids before writing them to the ledger.

The pre-submit checker visibility API returns only summary metadata and the compiled bundle hash. It does not expose raw `compiled_bundle` or `checker_configs`. Active-guide response behavior is preserved through a separate schema.

## Authorization

All seven endpoints require verified token auth and project setup operator access:

- allowed: `admin`, `project_manager`
- denied in v0.1: `worker`, `reviewer`, `finance`, `auditor`

## Evidence

Commands passed:

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
cd backend && .venv/bin/pytest tests/test_projects.py::test_project_setup_error_summary_redacts_sensitive_diagnostics tests/test_projects.py::test_project_setup_visibility_apis_show_automatic_setup_outputs tests/test_projects.py::test_project_setup_run_rejects_cross_context_worker_updates tests/test_projects.py::test_project_setup_run_records_enqueue_failure_without_leaking_error tests/test_projects.py::test_project_setup_visibility_apis_require_project_setup_role tests/test_projects.py::test_guide_activation_and_active_guide_retrieval tests/test_projects.py::test_pre_submit_visibility_requires_compiled_policy -vv
cd backend && .venv/bin/pytest tests/test_projects.py -q
cd backend && .venv/bin/pytest tests/test_projects.py::test_project_setup_visibility_apis_show_automatic_setup_outputs tests/test_projects.py::test_project_setup_visibility_apis_require_project_setup_role -q
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py
cd backend && .venv/bin/pytest tests/test_projects.py::test_create_guide_autostart_enqueues_without_inline_agent_execution tests/test_projects.py::test_create_source_snapshot_autostart_enqueues_latest_snapshot tests/test_projects.py::test_project_setup_worker_unexpected_error_does_not_leak_raw_exception -q
cd backend && .venv/bin/python -m ruff check app/workers/project_setup.py tests/test_projects.py
```

Key results:

- Targeted setup/project tests: 7 passed on final targeted run.
- Full project suite: 206 passed before the last optional test hardening.
- Final post-hardening visibility tests: 2 passed.
- API contract real API E2E: passed.
- External-review regression tests: 3 passed in 50.76s on final local run after the CI-specific test fix.
- Focused ruff check for worker/test changes: passed.
- Final stale wording scan: passed.
- Final Markdown link check: passed for 18 changed Markdown files.

## Internal Review

- Senior engineering: PASS WITH LOW RISKS
- QA/test: PASS WITH LOW RISKS
- Security/auth: PASS
- Product/ops: PASS WITH LOW RISKS
- Architecture: PASS
- Docs: PASS
- Reuse/dedup: PASS WITH LOW RISKS
- Test delta: PASS WITH LOW RISKS

All sub-agent sessions were closed.

## External Review

CodeRabbit completed review on PR #76. Valid comments were addressed in
`WS-POL-001-12-external-review-response.md`:

- strengthened the captured `setup_run_id` tests with persisted
  `ProjectSetupRun.id` and Celery task id checks
- updated Chunk 12 roadmap/status wording to open PR #76 under human review
- clarified the API contract drill wording
- fixed the internal security finding on raw unexpected worker exception logs
- fixed the CI failure by making the positive logger assertion deterministic

## Human Review Focus

- Confirm setup-run status names and terminal states are understandable.
- Confirm `ProjectSetupRun` remains a ledger and not a policy source of truth.
- Confirm operator access is limited to `admin` and `project_manager`.
- Confirm pre-submit checker visibility should hide `checker_configs` while active-guide keeps its existing policy context shape.

## Remaining Risks

- Full no-DB Terminal Benchmark drill proof remains assigned to WS-POL-001-14.
- `api_contract_e2e.py` uses manual setup records because there is no app-level deterministic project-agent runtime outside pytest fixtures.
- Setup-run status constants can be centralized later; Alembic migration literals should remain frozen.
