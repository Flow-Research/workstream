# Internal Review Evidence: WS-POL-002-02

## Chunk

WS-POL-002-02 - Post-Submit Derivation Agent And Resumable Setup Integration

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 67fb3caa302e03e5fdf99d4ad148c200d86348df

Reviewed at: 2026-07-11T09:55:12Z

Reviewer run ids: senior-engineering-019f508e-53c3-7280-850d-66fe80feca06, qa-test-019f508e-746c-7652-9eb9-0d2ec0accd1d, security-auth-019f508e-9b0b-7d12-b95d-a9eb3d86797d, product-ops-019f508e-b935-72e0-b33a-5b4f1d274cc4, architecture-019f508e-e9b6-7c83-9177-d63408ceb40b, docs-019f5096-c758-7b71-8338-92ae26544a6c, reuse-dedup-019f509a-e849-7b83-946b-c074979f07d9, test-delta-019f5091-3f3f-79f3-9eab-70338db24b7c, ci-integrity-019f509b-07a6-7071-a161-fc5ead52d079

## Reviewed Change

Branch: `codex/ws-pol-002-02-post-submit-derivation`

Scope:

- Adds setup-time `PostSubmitCheckerPolicyDerivationAgent` contract and OpenAI Agents SDK adapter output parsing.
- Extends the existing project setup queue/worker continuation after submission artifact policy approval and pre-submit checker compilation.
- Persists generated project `PostSubmitCheckerPolicy` rows with guide/source/effective-policy/pre-submit provenance and setup approval metadata.
- Blocks guide activation until generated post-submit policies are setup-approved.
- Adds automatic contributor submission handoff: authoritative pre-submit rerun, packet lock, `submission_finalized` audit, queued automatic pre-review gate, and repair-only `/finalize`.
- Adds Celery pre-review gate dispatch through `run_pre_review_gate`, system-actor audit attribution, requester provenance preservation, and failure/repair paths.
- Adds shared automatic-gate requester provenance helpers and shared Celery task-setting sync helpers.
- Adds atomic checker-run repository primitives for queued/running/failed automatic gate claims.
- Updates task/checker/project tests and real API scripts to use generated post-submit policy setup output instead of manual guide-body post-submit policy fields.
- Updates docs and loop artifacts to align the project-scoped post-submit policy, automatic gate, repair matrix, and submission-vs-task status ownership.

## Reviewer Results

These are Codex engineering-loop reviewer verdicts, not Workstream product
review decisions. Product review decisions remain `accept`, `needs_revision`,
and `reject`; internal reviewer agents report `PASS`, `PASS WITH LOW RISKS`,
`PASS AFTER FIXES`, or `FAIL` so process evidence stays separate from product
lifecycle records.

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Confirmed `requester_provenance_mismatch` removal from retryable failures is the smallest safe change and preserves service/repository boundaries. |
| QA/test | PASS | None | Confirmed enqueue, execution, and unknown-checker failures remain repairable while requester-provenance mismatch is terminal and tested. |
| security/auth | PASS | None | Confirmed requester-provenance mismatch fails closed, `/finalize` returns 409, and tampered automatic gate claims cannot be requeued. |
| product/ops | PASS WITH LOW RISKS | None | Required durable-evidence wording instead of unavailable queued-payload inspection; fixed before this evidence rebind. |
| architecture | PASS | None | Confirmed no runtime agent judgment, no per-task checker derivation, and engineering/product review decision separation remains intact. |
| docs | PASS AFTER FIXES | None | Required final evidence rebinding and external-response cleanup; fixed by this evidence-only rebind. |
| reuse/dedup | PASS WITH LOW RISKS | None | Found only an optional one-line wrapper cleanup; no helper bypass or behavior drift. |
| test delta | PASS | None | Confirmed the changed test is stronger and would fail against the old requeue-to-completed behavior. |
| CI integrity | PASS AFTER FIXES | None | Found no CI/test weakening; stale evidence was the only gate blocker and is fixed by this evidence-only rebind. |

## Valid Findings Addressed

- Reuse/dedup found duplicated requester-provenance contracts between task enqueue and checker validation. Added `backend/app/modules/checkers/pre_review_gate.py` and wired both services through it.
- Reuse/dedup found duplicated mutable Celery task-setting sync. Added `backend/app/workers/task_settings.py` and reused it from project setup and pre-review gate queues without importing the Celery app at module import time.
- QA found requester provenance could be audited before being validated against `submission_finalized`. The queued gate now validates persisted requester provenance before `pre_review_gate_started` or `evaluation_pending` mutation.
- Test-delta found eager dispatch failure was recorded but not repaired in tests. The test now restores the worker path, calls `/finalize`, and asserts the same run completes.
- Senior engineering found dispatch-failed audit could be written even when the checker-run enqueue-failure CAS missed. The task path now writes dispatch-failed audit only when `mark_pre_review_gate_enqueue_failed()` returns true, with a regression test.
- Product/ops found stale docs implying submission status owns review/revision lifecycle. Docs now state submission status stays `submitted`; task status owns evaluation/review/revision/acceptance/rejection lifecycle.
- Product/ops and docs found repair-matrix wording gaps for queued redispatch, stale running replacement, `pre_review_gate_execution_failed`, and non-repairable 409. Specs now match implemented behavior.
- CodeRabbit found `requester_provenance_mismatch` was incorrectly
  requeueable. The retryable failure set now only includes enqueue,
  execution, and unknown-checker failures; the tampered-provenance regression
  asserts `/finalize` returns 409 and leaves the failed run terminal.
- Product/ops found the docs should not tell operators to inspect a queued
  payload that is not retained as durable operator evidence. Specs and external
  review response now direct operators to locked submission audit,
  checker-run failure details, and retained worker logs if available.
- CodeRabbit found an awkward "required shared" phrase in the chunk contract.
  The sentence now says requester-provenance and Celery task-setting helpers
  were required to be shared.
- Architecture found helper files and `docs/architecture_system_architecture.md` were missing from the active chunk contract. The contract now explicitly allows those files for narrow lifecycle/provenance/helper alignment.
- CodeRabbit external findings from earlier passes were handled in `WS-POL-002-02-external-review-response.md`; valid findings were fixed and stale findings documented.

## Commands Run

```bash
cd backend && .venv/bin/pytest tests/test_tasks.py::test_finalize_repairs_locked_submission_with_missing_pre_review_gate tests/test_tasks.py::test_failed_pre_review_gate_repair_is_idempotent_while_queued tests/test_tasks.py::test_enqueue_failure_without_current_claim_skips_dispatch_failed_audit tests/test_tasks.py::test_eager_pre_review_gate_failure_after_submission_is_repairable tests/test_tasks.py::test_unknown_checker_gate_failure_is_repairable tests/test_tasks.py::test_nonrepairable_failed_gate_does_not_return_success tests/test_tasks.py::test_queued_gate_policy_error_is_failed_and_repairable tests/test_tasks.py::test_queued_gate_rejects_tampered_requester_provenance tests/test_tasks.py::test_queued_gate_fails_closed_when_lock_audit_is_missing tests/test_tasks.py::test_stale_queued_pre_review_gate_skips_before_task_status_check -q
cd backend && .venv/bin/pytest tests/test_projects.py::test_project_setup_queue_syncs_all_setup_task_settings -q
cd backend && .venv/bin/ruff check app/modules/checkers/pre_review_gate.py app/modules/checkers/service.py app/modules/checkers/gate_queue.py app/modules/projects/setup_queue.py app/modules/tasks/service.py app/workers/celery_app.py app/workers/task_settings.py tests/test_tasks.py tests/test_projects.py
cd backend && .venv/bin/python -m py_compile app/modules/checkers/pre_review_gate.py app/modules/checkers/service.py app/modules/checkers/gate_queue.py app/modules/projects/setup_queue.py app/modules/tasks/service.py app/workers/celery_app.py app/workers/task_settings.py tests/test_tasks.py tests/test_projects.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
rg -n "snorkel|termius|/home/abiorh/snorkel|terminal_benchmark_reviewer|build-seccomp-profile-reducer" . -S --glob '!backend/.venv/**' --glob '!**/.git/**'
git diff --check main...HEAD
```

Results:

- Focused automatic gate repair/provenance suite: 10 passed in 126.57s.
- Shared queue settings regression: 1 passed in 3.83s.
- Ruff: passed.
- Py compile: passed.
- Stale wording scan: passed.
- Markdown link check: passed for 24 changed Markdown files.
- Private-path/Snorkel leakage scan: no matches.
- Diff whitespace check: passed.

Earlier full-suite proof retained from this PR before final CAS-fence commits:

- Full backend suite after stale fixture repair: 442 passed in 4100.54s.
- Project and agent-runtime suite: 229 passed in 2037.08s.
- Task suite: 86 passed in 944.91s.
- Checker suite: 75 passed in 303.48s.
- Alembic suite: 6 passed in 67.47s.
- API contract real API drill passed after the CI bridge scope repair.
- Docstring coverage: 100.0%.
- Agent gates: 26 passed.
- Loop memory state check: passed.

## Remaining Risks

- Product/ops accepted a low visibility window where task status remains `submitted` with a queued current automatic gate until the Celery worker claims it and moves the task to `evaluation_pending`.
- A temporary CI/API-drill activation bridge remains until `WS-POL-002-03` replaces direct generated post-submit policy approval/setup-ledger marking with the server-owned approval API.
- External GitHub Actions and CodeRabbit must rerun after this evidence refresh is pushed.
