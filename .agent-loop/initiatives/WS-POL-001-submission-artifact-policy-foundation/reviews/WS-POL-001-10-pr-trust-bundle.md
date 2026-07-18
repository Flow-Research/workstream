# PR Trust Bundle: WS-POL-001-10

## Chunk

`WS-POL-001-10` - Pre-Submit Live Drill Hardening

## Goal

Fix the concrete pre-submit setup and intake gaps found during the real
Terminal Benchmark API drill before continuing post-submit work.

## Human-Approved Intent

The user explicitly asked to fix the first five pre-submit issues before moving
forward:

1. Duplicate guide versions must not bubble as 500s.
2. Worker profile setup must be possible through a real authenticated API, not
   direct DB seeding.
3. Project guide creation must support captured source material and
   representative task examples so agents are not forced to reason from guide
   markdown alone.
4. Active guide reads must show enough project pre-submit checker context for
   operators.
5. Failed pre-submit submission attempts must create no submission but still
   leave durable operator audit evidence.

Chunk contract:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-10-pre-submit-live-drill-hardening.md`

## What Changed

- Added `GuideVersionConflict` and mapped duplicate guide insert conflicts to
  HTTP 409.
- Added optional `source_snapshot` to guide creation, reusing the existing
  source snapshot capture and automatic setup enqueue path.
- Added `checker_names` and `checker_configs` to the active-guide
  `PreSubmitCheckerPolicySummaryResponse`; `compiled_bundle` remains excluded.
- Added `WorkerProfileUpsertRequest`, `WorkerProfileResponse`, and
  `POST /api/v1/workers/me/profile`.
- Added worker skill-tag normalization and fail-closed validation.
- Added durable `pre_submission_check_failed` task audit events for blocked
  submission-create attempts.
- Updated tests for all five acceptance criteria and reviewer-requested edge
  cases.
- Updated standing docs for worker self-profile setup and failed pre-submit
  audit semantics.
- Updated loop state/status and added this chunk contract.

## Why It Changed

The live Terminal Benchmark drill showed the lifecycle was mostly wired, but
parts still behaved like tests rather than a real Workstream workflow. This
chunk removes those rough edges while keeping the architecture project-scoped:
one active guide/source snapshot/effective project policy/project
`PreSubmitCheckerPolicy`, with tasks locking references to that context.

## Design Chosen

- Keep guide source material capture in the project module and reuse
  `_create_guide_source_snapshot_model`.
- Keep worker profile creation in the task module because claiming and worker
  assignment already depend on `WorkerProfile`.
- Derive worker identity only from verified Flow actor context.
- Keep failed pre-submit outcomes as `pre_submission_checker_failed` for
  submission-create responses and `pre_submission_check_failed` for internal
  task audit evidence.
- Expose checker names/configs to operators but not compiled checker bundle
  bodies.

## Alternatives Rejected

- Direct DB seeding for workers in real flows: rejected because it does not
  represent a human/API workflow.
- Reintroducing guide-owned artifact fields: rejected because
  `SubmissionArtifactPolicy` remains the artifact intake contract.
- Creating a submission row for failed pre-submit attempts: rejected because a
  failed pre-submit check means no valid submission exists yet.
- Broadly documenting all APIs in this chunk: rejected; only docs affected by
  changed public/operator behavior were updated.

## Scope Control

No migrations, checker internals, project-agent runtime changes, post-submit
policy redesign, review lifecycle, revision lifecycle, payment, reputation,
blockchain, frontend, or demo behavior was changed.

## Product Behavior

- Workers can create or refresh their own active profile before claiming a task.
- Workers without an active profile still cannot claim.
- Project operators can see checker names/configs on active guide reads.
- Blocked pre-submit submission-create attempts return
  `pre_submission_checker_failed`, create no submission, and write
  `pre_submission_check_failed` audit evidence for project operators.
- Product review decisions remain only `accept`, `needs_revision`, and `reject`.

## Acceptance Criteria Proof

- Duplicate guide version conflict: tested by
  `test_duplicate_guide_version_returns_conflict`.
- Guide-create source snapshot material: tested by
  `test_guide_creation_accepts_source_snapshot_items_for_agent_material`.
- Active-guide checker summary: tested by
  `test_guide_activation_and_active_guide_retrieval`.
- Worker self-profile create/refresh and claim: tested by
  `test_worker_can_create_profile_before_claiming_task`.
- Worker profile fail-closed validation and role gate: tested by
  `test_worker_profile_request_is_fail_closed_and_validated` and
  `test_worker_profile_requires_worker_role`.
- Nullable worker identity response contract: tested by
  `test_worker_profile_response_includes_nullable_identity_fields`.
- Failed pre-submit audit without submission: tested by
  `test_pre_submit_failure_writes_audit_event_without_submission`.

## Tests/Checks Run

```bash
cd backend && .venv/bin/python -m ruff check app/modules/projects/schemas.py app/modules/projects/service.py app/modules/tasks/router.py app/modules/tasks/schemas.py app/modules/tasks/service.py tests/test_projects.py tests/test_tasks.py
cd backend && .venv/bin/python -m pytest tests/test_projects.py -k 'duplicate_guide_version_returns_conflict or guide_creation_accepts_source_snapshot_items_for_agent_material or guide_activation_and_active_guide_retrieval' -q
cd backend && .venv/bin/python -m pytest tests/test_tasks.py -k 'worker_can_create_profile_before_claiming_task or worker_profile_response_includes_nullable_identity_fields or worker_profile_request_is_fail_closed_and_validated or worker_profile_requires_worker_role or worker_without_profile_cannot_claim_ready_task or pre_submit_failure_writes_audit_event_without_submission' -q
cd backend && .venv/bin/docstr-coverage app/modules/projects app/modules/tasks --config .docstr.yaml
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check
cd backend && .venv/bin/python -m pytest tests/test_projects.py tests/test_tasks.py tests/test_checkers.py -q
```

Result summary:

- ruff: passed.
- Focused project tests: 3 passed.
- Focused task tests: 6 passed.
- Docstring coverage: 100.0%.
- Markdown link check: passed for 10 changed Markdown files.
- Stale wording scan: passed.
- Diff whitespace check: passed.
- Full project/task/checker suite before the final nullable-response test
  addition: 310 passed; final focused worker/pre-submit rerun passed.

## Reviewer Results

Internal review evidence:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-10-internal-review-evidence.md`

Reviewed code SHA: `1b7d2e889fe1fd0460349b77c37e643a4e0c4cb0`

Reviewed diff digest before evidence files:
`67e2b7561d3688f6e588e5abe09317104da3bbd66ec97231f9f49b886801903b`

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Findings on conflict mapping and skill tags addressed. |
| QA/test | PASS | None | Requested nullable worker identity response coverage; addressed and passed rereview. |
| security/auth | PASS WITH LOW RISKS | None | Verified Flow-derived identity, role gate, bounded audit exposure, and nullable self-profile fields. |
| product/ops | PASS | None | Confirmed worker-owned profile setup, pre-submit failure audit evidence, and naming. |
| architecture | PASS WITH LOW RISKS | None | Broad `IntegrityError` concern addressed. |
| reuse/dedup | PASS WITH LOW RISKS | None | Minor profile construction duplication accepted. |
| docs | PASS WITH LOW RISKS | None | Endpoint inventory and loop metadata cleanup confirmed. |
| ci integrity | PASS AFTER FIXES | None | Evidence rebound to reviewed code SHA; only evidence/status files changed afterward. |
| test delta | PASS | None | Confirmed nullable identity-field regression test is meaningful and no assertions were weakened. |

## External Review

External review response:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-10-external-review-response.md`

CodeRabbit found three valid follow-up issues: evidence metadata, worker profile
response serialization, and endpoint inventory documentation. All are addressed.
GitHub Actions must rerun after the follow-up push.

## Remaining Risks

- Small duplication remains between worker/reviewer profile construction. It is
  not worth abstracting until another profile path appears.
- Post-submit policy derivation is still future work and intentionally not part
  of this chunk.

## Human Review Focus

- Confirm the worker profile endpoint is the right product boundary for
  authenticated workers before claim.
- Confirm failed pre-submit audit evidence is useful without confusing it with a
  product review decision.
- Confirm active-guide checker summary exposes enough operator context while
  keeping compiled bundles private.

## Human Merge Ownership

Only the user can approve and merge this PR. Codex must not merge it without
explicit user approval for that specific PR.
