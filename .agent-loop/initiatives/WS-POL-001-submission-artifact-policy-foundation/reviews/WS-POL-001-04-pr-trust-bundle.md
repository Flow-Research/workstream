# PR Trust Bundle: WS-POL-001-04

## Chunk

`WS-POL-001-04` - Post-Submit Checker Policy Provenance

## Goal

Separate post-submit checker policy naming and provenance from project
pre-submit checker policy and from the transitional
`locked_checker_policy_version` field.

## Human-Approved Intent

- Intent: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/INTENT.md`
- Plan: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/PLAN.md`
- Chunk contract: `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-04-post-submit-checker-policy-provenance.md`

## What Changed

- Added explicit locked post-submit checker policy id, version, hash, and body provenance to tasks, submissions, and durable checker runs.
- Added post-submit policy body/hash generation and locked-body parsing helpers.
- Made project activation and task readiness validate post-submit policy body/hash consistency.
- Made task screening copy immutable post-submit policy body/hash from active project setup.
- Made submission creation copy locked post-submit policy context from the task.
- Made durable checker runs copy and execute the submission-stamped locked post-submit policy body.
- Kept pre-submit checks non-durable: failed pre-submit intake still creates no submission and no durable checker run.
- Hid internal post-submit provenance, route fields, trigger provenance, and legacy checker policy version from worker-facing task, submission, checker-run, and audit responses.
- Added migration fail-closed preflight for legacy non-draft runtime rows before enforcing explicit post-submit provenance.
- Updated Week 1/Week 2 scripts and docs to use the new post-submit policy provenance boundary.

## Scope Control

Allowed implementation surface:

- `backend/alembic/versions/**`
- `backend/app/db/models.py`
- `backend/app/modules/projects/**`
- `backend/app/modules/tasks/**`
- `backend/app/modules/checkers/**`
- `backend/scripts/week1_dry_run.py`
- `backend/scripts/week1_api_e2e.py`
- `backend/scripts/week2_api_e2e.py`
- `backend/tests/**`
- Chunk-approved docs and `.agent-loop/` files

No frontend, human review decision implementation, revision resubmission,
payment/reputation/blockchain code, object storage, auth provider changes,
agent runtime redesign, pre-submit derivation redesign, or per-task checker
compilation was added.

## Product Behavior

Task screening locks post-submit checker policy context from the active project
guide-policy bundle:

```text
PostSubmitCheckerPolicy id
PostSubmitCheckerPolicy version
PostSubmitCheckerPolicy hash
PostSubmitCheckerPolicy immutable body
```

Submission creation stamps that context from the task. Durable checker runs
stamp the same context from the submission and execute the locked body.

Worker-facing behavior remains stable:

- pre-submit intake failure returns `pre_submission_checker_failed`
- checker-caused worker-fixable post-submit failure may surface as `needs_revision`
- setup/policy defects stay internal as `task_setup_blocked` or trusted checker retry
- product review decisions remain only `accept`, `needs_revision`, and `reject`

## Acceptance Criteria Proof

- Distinct pre-submit and post-submit provenance: `backend/app/modules/projects/post_submit_policy.py`, task/checker models, schemas, and docs.
- Task screening locks post-submit id/version/hash/body: `backend/app/modules/tasks/service.py`, `backend/tests/test_tasks.py`.
- Submission and checker run preserve locked context: `backend/app/modules/tasks/service.py`, `backend/app/modules/checkers/service.py`, `backend/tests/test_checkers.py`.
- Durable execution reads locked body, not live defaults or mutable setup rows: `backend/app/modules/checkers/service.py`, `backend/tests/test_checkers.py`.
- Missing/mismatched/invalid context fails closed before durable side effects: `backend/app/modules/checkers/service.py`, `backend/tests/test_checkers.py`.
- Pre-submit feedback remains non-durable: `backend/tests/test_tasks.py`, `backend/tests/test_checkers.py`.
- Worker-facing redaction: `backend/app/modules/tasks/service.py`, `backend/app/modules/checkers/service.py`, `backend/tests/test_tasks.py`, `backend/tests/test_checkers.py`.
- Migration safety: `backend/alembic/versions/0008_post_submit_checker_policy_provenance.py`, `backend/tests/test_alembic.py`.

## Tests And Checks Run

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

Result summary:

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
Agent gate result: REVIEW_REQUIRED for L1 migration/runtime/test risk; reviewed by CI integrity.
```

## Reviewer Results

Reviewed code SHA: `c2af838a2bef5a5504c43b7707d4d3248b1d8801`

Reviewed at: `2026-07-03T22:36:35Z`

Reviewer run IDs: see `WS-POL-001-04-internal-review-evidence.md`.

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Migration/runtime provenance reviewed. |
| QA/test | PASS AFTER FIXES | None | Redaction assertions strengthened. |
| security/auth | PASS | None | Worker surfaces and fail-closed behavior reviewed. |
| product/ops | PASS AFTER FIXES | None | Status wording and worker/operator semantics reviewed. |
| architecture | PASS WITH LOW RISKS | None | Legacy physical table naming remains contained. |
| docs | PASS AFTER FIXES | None | Roadmap and loop-state wording cleaned. |
| reuse/dedup | PASS | None | Shared helpers reused. |
| test delta | PASS AFTER FIXES | None | Test coverage gap closed. |
| CI integrity | PASS WITH LOW RISKS | None | Agent gate risk accepted; no CI weakening found. |

## External Review

External review is tracked separately in
`WS-POL-001-04-external-review-response.md`.

Result summary:

```text
CodeRabbit passed.
Agent Gates passed.
Backend passed.
Week 1 API Demo UI passed.
```

Internal review evidence does not replace external review.

## Remaining Risks

- Physical storage still uses `checker_policies` for v0.1 compatibility. New code should avoid treating generic checker policy naming as runtime authority.
- Legacy `locked_checker_policy_version` remains admin-visible context on durable checker runs; worker surfaces redact it and runtime uses `locked_post_submit_checker_policy_*`.
- Revision resubmission proof remains deferred to `WS-POL-001-05`.

## Human Review Focus

Please inspect:

- Migration `0008` fail-closed preflight and post-submit provenance constraints.
- Task -> submission -> checker-run locked policy propagation.
- Locked policy body execution instead of live default constants or mutable setup rows.
- Worker-facing API redaction of internal route/provenance fields.
- Separation between `pre_submission_checker_failed`, internal setup routing, and user-facing `needs_revision`.

## Human Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
