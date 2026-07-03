# Internal Review Evidence: WS-POL-001-04

## Chunk

WS-POL-001-04

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: c2af838a2bef5a5504c43b7707d4d3248b1d8801

Reviewed at: 2026-07-03T22:36:35Z

Reviewer run IDs: 019f2a0a-7a27-7131-8ceb-909a702d2010, 019f2a0a-b64d-7710-ad09-d3aececdb9ef, 019f2a0a-d6a5-79c1-95f8-fdd43bcd1297, 019f2a0a-fe3c-7a23-a4ef-3c9ca5005aac, 019f2a0b-2135-74e0-881e-989981a2824c, 019f2a0b-4d74-7cf1-8e80-0f981265ae79, 019f2a0e-73fe-7e70-81f6-fd58b104c044, 019f2a0e-9508-7f62-9539-9ed563d3abfe, 019f2a12-5bdf-7a03-a3c2-98622dc1a2c3, 019f2a12-7cc4-7d50-b5ec-9cc1dde06cb5, 019f2a12-a5be-7df2-b72b-761b88ff2560, 019f2a15-a9a3-7313-86f4-b6896907f6ae, 019f2a15-cc69-7bc3-bea2-c195aafcbc81, 019f2a17-be8e-7911-a9e8-6dc7c2685d3b, 019f2a17-e105-7960-81e4-091286d0716b, 019f2a1b-eb0d-79b2-937d-b4518a83094c, 019f2a1c-16e8-7c71-84e2-172fc227f96d, 019f2a1c-36fa-7ee2-a061-57fc13dd1d07, 019f2a1c-5a55-71e0-8682-56e7d8778ec8, 019f2a1c-8a86-7361-94f2-02cf17926c24, 019f2a1c-b921-7192-956b-fac88ed7ecf9, 019f2a1f-0c97-7ae1-ba1b-650a25fb077c, 019f2a1f-3c6d-7581-a092-66e969afecb0, 019f2a45-d4bc-7221-a97a-2686e83a67f8

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Confirmed post-submit policy provenance, migration preflight, worker redaction, and scope boundaries. |
| qa/test | PASS AFTER FIXES | None | Verified acceptance coverage after task/submission redaction assertions were strengthened. |
| security/auth | PASS | None | Confirmed client-supplied locked fields are rejected, worker surfaces hide internals, and checker execution fails closed before side effects. |
| product/ops | PASS AFTER FIXES | None | Confirmed worker/operator wording after `pre_submission_checker_failed` cleanup and loop-state label clarification. |
| architecture | PASS WITH LOW RISKS | None | Low residual: physical `checker_policies` storage and legacy admin-visible version remain compatibility context; new execution uses post-submit provenance. |
| docs | PASS AFTER FIXES | None | Confirmed roadmap/status wording after canonical token and loop-state cleanup. |
| reuse/dedup | PASS | None | Confirmed reuse of `post_submit_checker_policy_body`, `post_submit_checker_policy_hash`, parser, and canonical hashing helpers. |
| test delta | PASS AFTER FIXES | None | Confirmed strengthened task/submission response redaction assertions and no weakened tests or skips. |
| ci integrity | PASS WITH LOW RISKS | None | Confirmed no workflow/package/test gate weakening; deterministic agent gate correctly requires review for the large L1 migration/runtime diff. |

## Valid Findings Addressed

- Fixed worker-facing task response coverage after product/ops found the legacy `locked_checker_policy_version` risk. `TaskResponse` does not expose that field, and tests now assert it is absent.
- Strengthened task and submission redaction tests to enumerate `locked_post_submit_checker_policy_id`, `locked_post_submit_checker_policy_version`, `locked_post_submit_checker_policy_hash`, and `locked_post_submit_checker_policy_body`.
- Reused `post_submit_checker_policy_hash` in project service instead of leaving the shared helper unused.
- Repaired roadmap wording so the real API drill uses canonical `pre_submission_checker_failed` for pre-submit intake blocking and preserves checker-caused `needs_revision` for worker-fixable post-submit failures.
- Updated loop memory so `WS-POL-001-04` is review-complete but not merged, `WS-POL-001-05` remains inactive, and prior merge hashes are labeled as last-merged context.
- Added CI-integrity review after the deterministic agent gate returned `REVIEW_REQUIRED` for the large migration/runtime/test diff.

## Commands Run

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_loop_memory_state.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
git diff --check
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_tasks.py::test_worker_task_response_redacts_locked_policy_hashes tests/test_tasks.py::test_assigned_worker_submits_v1_and_task_moves_to_submitted
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_tasks.py::test_worker_task_response_redacts_locked_policy_hashes tests/test_tasks.py::test_screening_uses_persisted_post_submit_policy_body_after_default_drift tests/test_tasks.py::test_submission_uses_locked_post_submit_policy_body_after_setup_mutation tests/test_checkers.py::test_checker_run_uses_locked_post_submit_policy_body_after_setup_mutation tests/test_checkers.py::test_locked_post_submit_policy_parser_uses_persisted_body_hash
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_checkers.py tests/test_tasks.py tests/test_projects.py
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests
```

## Results

```text
Ruff app/tests/scripts passed.
Docstring coverage passed: 100.0% (542/542).
Markdown link check passed for 15 changed Markdown files.
Stale wording check passed.
Loop memory state check passed.
git diff --check passed.
Focused redaction tests passed: 2 passed in 35.62s.
Focused post-submit provenance tests passed: 5 passed in 86.67s.
Module suite passed: 292 passed in 2790.99s.
Full Postgres-backed backend suite passed on reviewed SHA: 323 passed in 2387.87s.
Agent gate result: REVIEW_REQUIRED because this is a large L1 migration/runtime/test diff touching risk-sensitive paths.
CI-integrity review accepted the REVIEW_REQUIRED result and found no bypass or gate weakening.
```

## Remaining Risks

- The physical table remains `checker_policies` while code/API naming treats it as `PostSubmitCheckerPolicy` storage. This is contained compatibility for v0.1; future migrations should avoid re-promoting generic checker-policy naming.
- `locked_checker_policy_version` remains admin-visible legacy context on durable checker-run provenance. New runtime authority uses `locked_post_submit_checker_policy_*`, and worker responses redact legacy/internal fields.
- `WS-POL-001-05` still owns revision resubmission proof and public lifecycle coverage.
