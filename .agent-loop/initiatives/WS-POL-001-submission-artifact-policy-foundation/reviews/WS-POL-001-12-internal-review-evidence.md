# Internal Review Evidence: WS-POL-001-12

## Chunk

WS-POL-001-12

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 1465ddb2c8c40eb3b7cc8f1e2befd3971cea53a5

Reviewed at: 2026-07-07T18:40:28Z

Reviewer run IDs: senior-engineering-review-019f3d21-2c35-7923-ad77-4e3aeefc653e, senior-engineering-rerun-019f3d2f-7f7d-7ec1-96c9-72ce50010243, senior-engineering-final-019f3dcf-c4a5-7e00-95bc-fd65855864d4, qa-test-review-019f3d21-36bb-7881-8b01-74405a83a9af, qa-test-final-019f3dcb-a346-7d52-ac31-e00053b0c81d, security-auth-review-019f3d21-3c05-7fe3-8c98-a88e15ee82ac, security-auth-rerun-019f3d2f-6ae2-7601-bf97-3e43070480c3, security-auth-final-019f3dcb-d1a9-7ed0-be64-b449f854ae9e, product-ops-review-019f3d21-46f2-7330-ab33-2e31a174a8c2, product-ops-rerun-019f3d2f-8d32-7232-ba81-d7b721bce0a5, product-ops-final-019f3dcc-0208-7c72-8896-8e0526be1904, architecture-review-019f3d21-502c-7331-adc0-8c50c43fad2c, architecture-rerun-019f3d2f-78ac-72d1-ba9b-146c4dc04ec6, architecture-final-019f3dcf-ee6a-7e60-aa73-b62d38ffab1d, docs-review-019f3d21-5ad7-7f20-9f77-0cc747ded03d, docs-final-019f3dcc-3de1-70e1-8320-91769dc877ac, reuse-dedup-review-019f3d2f-a189-70f2-ae58-836448d74835, reuse-dedup-final-019f3dd0-156e-7c93-9947-8631f68d5292, test-delta-review-019f3d2f-b8f5-7a00-88c8-ac5e54158b13, test-delta-rerun-019f3d3a-da3a-7372-9082-b41fa77b5236, test-delta-final-019f3dd0-3ee6-78a3-9a42-518bb77cf5ed, test-delta-ci-fix-019f3ddf-a0e1-7563-8224-7fba49e5eb82

After the reviewed SHA, only review evidence files changed.

## Reviewed Change

Scope:

- Adds `ProjectSetupRun` as a non-authoritative ledger for automatic project setup execution.
- Persists setup runs before enqueue, records Celery task ids, and records `enqueue_failed` when enqueue fails.
- Updates the project setup worker to validate setup-run context, advance setup-run status, and validate output ids before recording them.
- Adds seven operator-only project setup and policy visibility APIs for setup run, sufficiency report, submission artifact policy, effective project submission artifact policy, and compiled project pre-submit checker policy state.
- Keeps policy truth in guide source snapshot, sufficiency report, submission artifact policy, effective policy, and pre-submit checker policy records; setup-run output ids are only pointers.
- Hides raw compiled checker bundle and checker configs from the new pre-submit checker visibility endpoint while preserving active-guide response behavior.
- Fails closed for public setup-run error summaries so operator APIs and worker task results do not expose tokens, private object keys, local paths, signed URLs, or raw stack traces.
- Updates docs and initiative planning for APIs 1-7 and records WS-POL-001-13/14 as later chunks.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Fixed fail-closed redaction, output scope validation, active-guide schema boundary, and removed dead queue preflight. |
| QA/test | PASS WITH LOW RISKS | None | Verified setup-run id correlation now compares queue payloads to persisted `ProjectSetupRun.id` and Celery task id. |
| security/auth | PASS | None | Verified unexpected worker failures no longer log raw exception text or tracebacks and visibility APIs remain scoped. |
| product/ops | PASS WITH LOW RISKS | None | Confirmed PR #76 is represented as open and under human review, not merged. |
| architecture | PASS | None | Split active-guide checker schema, removed unscoped effective-policy helper, and wrapped latest snapshot ambiguity. |
| docs | PASS | None | Confirmed exact seven API paths are documented and ProjectSetupRun is consistently described as a ledger; evidence artifacts updated after external review. |
| reuse/dedup | PASS WITH LOW RISKS | None | Accepted low-risk test helper duplication for the focused worker regression. |
| test delta | PASS WITH LOW RISKS | None | Verified setup-run correlation tests and unexpected worker error regression strengthen coverage. |

## Valid Findings Addressed

- Changed setup-run public error handling to fail closed for every non-empty summary.
- Updated enqueue failure and worker error handling to store/log/return sanitized public summaries only.
- Added worker setup-run context validation before running guide sufficiency or policy derivation.
- Added setup-run output validation so sufficiency report and submission artifact policy ids must match project, guide, guide version, source snapshot id, and source snapshot hash.
- Split the active-guide checker policy response from the new redacted visibility response so APIs 1-7 do not silently alter the existing active-guide contract.
- Removed the unused queue readiness probe after enqueue failure became ledger state rather than a pre-persist blocker.
- Removed the unscoped current effective policy repository helper.
- Ordered latest setup-run lookup by source snapshot capture time before setup-run creation time.
- Broadened authorization tests to prove `admin` and `project_manager` can read these endpoints while `worker`, `reviewer`, `finance`, and `auditor` cannot.
- Added cross-project and same-project/different-guide scoping checks for setup-run latest, list endpoints, item GET endpoints, effective policy, and pre-submit checker policy reads.
- Preserved active-guide `checker_configs` while ensuring the new pre-submit visibility summary omits raw checker authority.
- Addressed CodeRabbit's tautological `setup_run_id` assertion by comparing captured enqueue payloads to persisted `ProjectSetupRun.id` and recorded Celery task id.
- Updated roadmap and loop status wording so PR #76 is represented as open and under human review, not merged.
- Replaced raw unexpected worker exception logging with sanitized structured logging and added regression coverage for result, persisted setup-run error, and log output.
- Added deterministic positive logger assertions for the unexpected worker failure path.

## Commands Run

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
rg -n "DB inspection|direct DB|setup-runs/latest|ProjectSetupRun" docs backend examples .agent-loop
cd backend && .venv/bin/pytest tests/test_projects.py::test_project_setup_error_summary_redacts_sensitive_diagnostics tests/test_projects.py::test_project_setup_visibility_apis_show_automatic_setup_outputs tests/test_projects.py::test_project_setup_run_rejects_cross_context_worker_updates tests/test_projects.py::test_project_setup_run_records_enqueue_failure_without_leaking_error tests/test_projects.py::test_project_setup_visibility_apis_require_project_setup_role tests/test_projects.py::test_guide_activation_and_active_guide_retrieval tests/test_projects.py::test_pre_submit_visibility_requires_compiled_policy -vv
cd backend && .venv/bin/pytest tests/test_projects.py -q
cd backend && .venv/bin/pytest tests/test_projects.py::test_project_setup_visibility_apis_show_automatic_setup_outputs tests/test_projects.py::test_project_setup_visibility_apis_require_project_setup_role -q
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py
cd backend && .venv/bin/pytest tests/test_projects.py::test_create_guide_autostart_enqueues_without_inline_agent_execution tests/test_projects.py::test_create_source_snapshot_autostart_enqueues_latest_snapshot tests/test_projects.py::test_project_setup_worker_unexpected_error_does_not_leak_raw_exception -q
cd backend && .venv/bin/python -m ruff check app/workers/project_setup.py tests/test_projects.py
```

Results:

- Ruff: passed.
- Stale wording scan: passed.
- Markdown link check: passed for 15 changed Markdown files.
- Scope/stale proof scan: only expected setup-run docs and future DB-inspection-removal chunk references remained.
- Targeted setup/project tests: 7 passed in 186.41s on final targeted run.
- Full project test suite: 206 passed in 2269.22s before final same-project/different-guide list-scope hardening; the post-hardening full-suite process exited cleanly but its interrupted terminal summary was not recoverable.
- Final post-hardening targeted visibility tests: 2 passed in 38.57s.
- API contract real API E2E: passed after final implementation changes.
- CodeRabbit/security targeted regression tests: 3 passed in 29.13s on final local run.
- CI-specific deterministic logger regression rerun: 3 passed in 50.76s locally.
- Focused ruff check for worker/test changes: passed.
- Final stale wording scan: passed.
- Final Markdown link check: passed for 18 changed Markdown files.

## Remaining Risks

- `api_contract_e2e.py` still uses manual setup records for deterministic local execution and does not call `setup-runs/latest`; full no-DB Terminal Benchmark drill proof is assigned to WS-POL-001-14.
- Same-project/different-guide list scoping was hardened in targeted tests after test-delta review. Full project suite was interrupted during output capture, so final proof combines prior full-suite pass plus final targeted visibility and external-review regression passes.
- Setup-run statuses are repeated across migration/model/service/docs. A future cleanup can centralize runtime constants while keeping Alembic literals frozen.
