# External Review Response: WS-POL-001-12

## Comments Addressed

- CodeRabbit: `backend/tests/test_projects.py` had a tautological
  `setup_run_id` assertion. Added explicit length/truthiness assertions and
  DB-backed checks that captured enqueue payloads match the persisted
  `ProjectSetupRun.id` and recorded Celery task id.
- CodeRabbit: `docs/roadmap_status.md` still described Chunk 12 as in
  implementation. Updated it to say the chunk is implemented in open PR #76
  and under human review.
- CodeRabbit: `docs/roadmap_status.md` used awkward wording around the API
  contract drill. Reworded the sentence for clarity.
- Internal security review: the generic setup worker exception path used
  `logger.exception`, which could leak raw exception text and tracebacks.
  Replaced it with sanitized structured logging and added regression coverage
  for task result, persisted setup-run state, and captured logs.
- Internal test-delta review: the first positive log assertion relied on
  `caplog` propagation and failed in GitHub Actions. Replaced it with a
  deterministic monkeypatched `logger.error` capture that asserts the exact
  structured payload and secret-free log data.
- Internal docs/product review: trust evidence and status artifacts were stale
  after external-review fixes. Rebound internal evidence to reviewed code SHA
  `1465ddb2c8c40eb3b7cc8f1e2befd3971cea53a5` and updated this response plus
  the PR trust bundle.

## Comments Deferred

None.

## Human Decisions Needed

None for these comments. Human merge review is still required for PR #76.

## Commands Rerun

- `cd backend && .venv/bin/pytest tests/test_projects.py::test_create_guide_autostart_enqueues_without_inline_agent_execution tests/test_projects.py::test_create_source_snapshot_autostart_enqueues_latest_snapshot tests/test_projects.py::test_project_setup_worker_unexpected_error_does_not_leak_raw_exception -q`
  - Result: 3 passed in 50.76s on the final local run after the CI-specific test fix.
- `cd backend && .venv/bin/python -m ruff check app/workers/project_setup.py tests/test_projects.py`
  - Result: passed.
- `python3 scripts/check_stale_workstream_wording.py`
  - Result: passed.
- `python3 scripts/check_markdown_links.py`
  - Result: passed for 18 changed Markdown files.
- Internal reviewer reruns after external-review fixes:
  - senior engineering: PASS WITH LOW RISKS
  - QA/test: PASS WITH LOW RISKS
  - security/auth: PASS
  - product/ops: PASS WITH LOW RISKS after evidence artifacts are committed
  - architecture: PASS
  - docs: PASS after evidence artifacts are committed
  - reuse/dedup: PASS WITH LOW RISKS
  - test delta: PASS WITH LOW RISKS
  - CI-specific test-delta rerun: PASS

## Remaining Risks

- `WS-POL-001-13` and `WS-POL-001-14` still own the remaining visibility and
  finalize APIs before the Terminal Benchmark no-DB drill can be repeated.
