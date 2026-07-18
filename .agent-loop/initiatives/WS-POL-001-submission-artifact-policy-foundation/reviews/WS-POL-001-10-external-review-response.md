# External Review Response: WS-POL-001-10

## Scope

External review feedback for PR #72: `Harden pre-submit live drill flows`.

Internal sub-agent evidence is tracked separately in:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-10-internal-review-evidence.md`

## CodeRabbit Review

CodeRabbit reviewed PR #72 on 2026-07-06 and posted three actionable comments.

| Source | Finding | Severity | Status | Response |
|---|---|---:|---|---|
| CodeRabbit | Internal review evidence was not in the parser-required format; the `test delta` row and reviewed revision metadata could not pass `scripts/check_internal_review_evidence.py`. | Major | Fixed | Rebound evidence to reviewed code SHA `1b7d2e889fe1fd0460349b77c37e643a4e0c4cb0`, normalized reviewer rows to known tracks, used parseable reviewer run IDs, and limited post-review changes to evidence/status files. |
| CodeRabbit | `POST /api/v1/workers/me/profile` used `response_model_exclude_none=True`, dropping required nullable `display_name` and `email` fields. | Minor | Fixed | Removed `response_model_exclude_none=True` from the route and added `test_worker_profile_response_includes_nullable_identity_fields`. |
| CodeRabbit | `POST /api/v1/workers/me/profile` was documented in Security/Auth but missing from the chunk 4 endpoint inventory. | Minor | Fixed | Added the endpoint to `docs/spec_chunk_4_task_queue_assignment.md` under API Impact. |

## Verification

```bash
cd backend && .venv/bin/python -m ruff check tests/test_tasks.py app/modules/tasks/router.py
cd backend && .venv/bin/python -m pytest tests/test_tasks.py -k 'worker_can_create_profile_before_claiming_task or worker_profile_response_includes_nullable_identity_fields or worker_profile_request_is_fail_closed_and_validated or worker_profile_requires_worker_role or worker_without_profile_cannot_claim_ready_task or pre_submit_failure_writes_audit_event_without_submission' -q
python3 scripts/check_markdown_links.py docs/spec_chunk_4_task_queue_assignment.md
python3 scripts/check_stale_workstream_wording.py
git diff --check
```

Results:

- ruff: passed.
- Focused worker/pre-submit task tests: 6 passed, 59 deselected.
- Markdown link check: passed for 10 changed Markdown files.
- Stale wording scan: passed.
- Diff whitespace check: passed.

## Remaining External State

GitHub Actions and CodeRabbit must rerun after this response and fix are pushed.
