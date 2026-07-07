# Internal Review Evidence: WS-POL-001-12

## Chunk

WS-POL-001-12

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: c143b54b62d6325a1d4787116e692fedfc5716f2

Reviewed at: 2026-07-07T17:11:38Z

Reviewer run IDs: senior-engineering-review-019f3d21-2c35-7923-ad77-4e3aeefc653e, senior-engineering-rerun-019f3d2f-7f7d-7ec1-96c9-72ce50010243, qa-test-review-019f3d21-36bb-7881-8b01-74405a83a9af, security-auth-review-019f3d21-3c05-7fe3-8c98-a88e15ee82ac, security-auth-rerun-019f3d2f-6ae2-7601-bf97-3e43070480c3, product-ops-review-019f3d21-46f2-7330-ab33-2e31a174a8c2, product-ops-rerun-019f3d2f-8d32-7232-ba81-d7b721bce0a5, architecture-review-019f3d21-502c-7331-adc0-8c50c43fad2c, architecture-rerun-019f3d2f-78ac-72d1-ba9b-146c4dc04ec6, docs-review-019f3d21-5ad7-7f20-9f77-0cc747ded03d, reuse-dedup-review-019f3d2f-a189-70f2-ae58-836448d74835, test-delta-review-019f3d2f-b8f5-7a00-88c8-ac5e54158b13, test-delta-rerun-019f3d3a-da3a-7372-9082-b41fa77b5236, test-delta-final-019f3d69-1863-7923-809d-dbb327c19952

After the reviewed SHA, only evidence and status files changed.

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
| QA/test | PASS WITH LOW RISKS | None | Added latest-run ordering by source snapshot and denied-role coverage beyond workers. |
| security/auth | PASS | None | Fixed public setup-run error summaries and worker logs/results to avoid raw exception leakage. |
| product/ops | PASS WITH LOW RISKS | None | Accepted that full setup-run proof in real API drill belongs to WS-POL-001-14 while integration tests cover this chunk. |
| architecture | PASS | None | Split active-guide checker schema, removed unscoped effective-policy helper, and wrapped latest snapshot ambiguity. |
| docs | PASS | None | Confirmed exact seven API paths are documented and ProjectSetupRun is consistently described as a ledger. |
| reuse/dedup | PASS WITH LOW RISKS | None | Addressed schema duplication by subclassing the active-guide checker schema and removed dead redaction regexes. |
| test delta | PASS WITH LOW RISKS | None | Added cross-project, same-project/different-guide, admin allow, and denied-role visibility coverage. |

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

## Remaining Risks

- `api_contract_e2e.py` still uses manual setup records for deterministic local execution and does not call `setup-runs/latest`; full no-DB Terminal Benchmark drill proof is assigned to WS-POL-001-14.
- Same-project/different-guide list scoping was hardened in targeted tests after test-delta review. Full project suite was interrupted during output capture, so final proof combines prior full-suite pass plus final targeted visibility pass.
- Setup-run statuses are repeated across migration/model/service/docs. A future cleanup can centralize runtime constants while keeping Alembic literals frozen.
