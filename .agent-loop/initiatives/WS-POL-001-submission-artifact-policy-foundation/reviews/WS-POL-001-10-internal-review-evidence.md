# Internal Review Evidence: WS-POL-001-10

## Chunk

WS-POL-001-10

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 1b7d2e889fe1fd0460349b77c37e643a4e0c4cb0

Reviewed working diff digest before evidence files:
67e2b7561d3688f6e588e5abe09317104da3bbd66ec97231f9f49b886801903b

Reviewed at: 2026-07-06T10:38:01Z

Reviewer run IDs: senior-engineering-review-019f36f1-72aa-7bd2-921e-2e667b03b7d3, qa-test-review-019f36f1-74e2-7d73-b9f5-7a5415f49133, security-auth-review-019f36f1-793d-7b53-b7c6-d12e71063ac3, product-ops-review-019f36f1-7de2-7fe1-a9ea-a3c46fd34605, docs-review-019f36f1-8264-7c33-8448-c7c470678a9b, test-delta-review-019f36f1-86b1-7e93-947b-2d36ef32c931, qa-rereview-019f36fd-6300-7081-84ae-f4bb6072a142, architecture-review-019f36fd-691c-7181-93c7-c0691bcc7078, reuse-dedup-review-019f36fd-7241-77a1-9da3-6aa31e10e7ee, ci-integrity-review-019f36fd-89df-7a41-bb1c-53d86e08f122, test-delta-rereview-019f36fd-aa2e-7ff0-a997-45d4b3824f48

After the reviewed SHA, only evidence and status files changed.

## Reviewed Change

Scope:

- Maps duplicate guide versions to a 409 conflict instead of an unhandled DB
  error.
- Allows guide creation to include immutable source-snapshot items, including
  representative task examples, so the existing automatic setup pipeline has
  full setup material.
- Exposes project pre-submit checker names and configs in the active-guide
  summary while still excluding the compiled checker bundle body.
- Adds `POST /api/v1/workers/me/profile` so workers can create or refresh their
  own active profile from verified Flow identity before claim.
- Writes durable `pre_submission_check_failed` task audit evidence when
  submission creation is blocked by pre-submit checks, while creating no
  submission version.
- Updates standing docs to distinguish no submission-created audit event from
  the new failed-attempt task audit evidence.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Confirmed the CodeRabbit follow-up route and docs changes are minimal; evidence rebind required before merge. |
| QA/test | PASS | None | Initial review requested nullable worker profile response coverage; rereview confirmed `display_name` and `email` stay serialized as null. |
| security/auth | PASS WITH LOW RISKS | None | Verified worker profile identity is derived from `ActorContext`, role-gated, bounded in audit exposure, and nullable self-profile fields are not a new exposure. |
| product/ops | PASS | None | Confirmed worker-owned profile setup, pre-submit failure audit evidence, and naming stay aligned with Workstream workflow. |
| architecture | PASS WITH LOW RISKS | None | Confirmed route/docs/test changes stay inside WS-POL-001-10 and do not change pre-submit architecture boundaries. |
| reuse/dedup | PASS WITH LOW RISKS | None | Implementation reuses `TaskRepository.upsert_worker_profile`; evidence gate issue addressed in this evidence-only update. |
| docs | PASS WITH LOW RISKS | None | Confirmed worker profile endpoint inventory and task assignment docs; noted loop metadata cleanup, addressed here. |
| ci integrity | PASS AFTER FIXES | None | Initial review required evidence rebinding to reviewed code SHA `1b7d2e889fe1fd0460349b77c37e643a4e0c4cb0`; this evidence-only update applies it. |
| test delta | PASS | None | Reviewed code sha `1b7d2e889fe1fd0460349b77c37e643a4e0c4cb0`; reviewer run ids `019f36f1-86b1-7e93-947b-2d36ef32c931`, `019f36fd-aa2e-7ff0-a997-45d4b3824f48`; confirmed the nullable identity-field test is meaningful and no assertions were weakened. |

## Valid Findings Addressed

- Narrowed `create_guide` duplicate-version handling so `GuideVersionConflict`
  maps only the guide insert/flush integrity failure, not later optional policy
  or source-snapshot persistence.
- Added worker profile skill-tag normalization: strip, lowercase, dedupe, reject
  blank tags, and cap each tag at 64 characters.
- Added worker profile request negative tests for unknown client identity fields,
  blank tags, overlong tags, non-worker role access, and public refresh behavior.
- Added worker profile response contract coverage proving nullable
  `display_name` and `email` fields remain serialized as explicit null values.
- Updated docs to state that failed pre-submit submission-create attempts write
  `pre_submission_check_failed` task audit evidence while creating no
  `Submission`, submission version, task transition to `submitted`, or
  submission-created audit event.
- Updated task assignment docs to document the worker-owned profile create or
  refresh endpoint and its Flow-token-derived identity boundary.
- Updated the chunk contract to allow only the specific standing docs needed by
  the docs reviewer findings.
- Rebound internal review evidence to implementation commit
  `1b7d2e889fe1fd0460349b77c37e643a4e0c4cb0`; only evidence and status files
  changed after that reviewed SHA.

## Commands Run

```bash
cd backend && .venv/bin/python -m ruff check app/modules/projects/schemas.py app/modules/projects/service.py app/modules/tasks/router.py app/modules/tasks/schemas.py app/modules/tasks/service.py tests/test_projects.py tests/test_tasks.py
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'duplicate_guide_version_returns_conflict or guide_creation_accepts_source_snapshot_items_for_agent_material or guide_activation_and_active_guide_retrieval' -q
cd backend && .venv/bin/python -m pytest tests/test_tasks.py -k 'worker_can_create_profile_before_claiming_task or worker_profile_response_includes_nullable_identity_fields or worker_profile_request_is_fail_closed_and_validated or worker_profile_requires_worker_role or worker_without_profile_cannot_claim_ready_task or pre_submit_failure_writes_audit_event_without_submission' -q
cd backend && .venv/bin/docstr-coverage app/modules/projects app/modules/tasks --config .docstr.yaml
python3 scripts/check_markdown_links.py docs/spec_chunk_4_task_queue_assignment.md
python3 scripts/check_stale_workstream_wording.py
git diff --check
cd backend && .venv/bin/python -m pytest tests/test_projects.py tests/test_tasks.py tests/test_checkers.py -q
```

Results:

- ruff: passed.
- Focused project tests: 3 passed, 196 deselected.
- Focused task tests: 6 passed, 59 deselected.
- Docstring coverage: 100.0%.
- Markdown link check: passed for 10 changed Markdown files.
- Stale wording scan: passed.
- Diff whitespace check: passed.
- Full project/task/checker suite before the final nullable-response test
  addition: 310 passed in 41:18; final focused worker/pre-submit rerun passed.

## Remaining Risks

- The worker and reviewer profile construction paths still have small duplicate
  actor-claim mapping logic. This is intentionally left as-is until another
  profile path appears; adding an abstraction now would not simplify the chunk.
- This chunk does not implement post-submit policy derivation or review
  lifecycle behavior. That remains out of scope.
