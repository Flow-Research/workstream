# PR Trust Bundle: WS-POL-001-08

## Chunk

`WS-POL-001-08` - Celery Project Setup Pipeline

## Goal

Make project guide setup run automatically after guide material is captured.

The normal path is now:

```text
ProjectGuide / GuideSourceSnapshot
-> Celery project setup job
-> ProjectGuideSufficiencyAgent
-> stop if blocked
-> SubmissionArtifactPolicyDerivationAgent
-> draft SubmissionArtifactPolicy for human approval
```

## Human-Approved Intent

The user explicitly corrected the architecture:

- project setup must be async and automatic, not a manual trigger path;
- use Celery for this product-job boundary, not FastAPI background tasks;
- focus on pre-submit setup first before post-submit expansion;
- project owners provide project guide/payment material, while Workstream runs
  the internal guide sufficiency and policy derivation process;
- no backward-compatibility aliases are needed while Workstream is still in
  build phase; removed request/body fields should be removed completely.

Chunk contract:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-08-celery-project-setup-pipeline.md`

## What Changed

- Added Celery worker infrastructure under `backend/app/workers/`.
- Added a project setup queue boundary under
  `backend/app/modules/projects/setup_queue.py`.
- Added explicit Celery settings and local Redis service.
- `ProjectService.create_guide` now creates the guide-body source snapshot and
  enqueues the project setup pipeline when autostart is enabled.
- `ProjectService.create_guide_source_snapshot` now enqueues setup for later
  draft source snapshots.
- The Celery task runs sufficiency first, stops before derivation if blocked,
  and creates only a draft submission artifact policy on pass/warning.
- Removed discarded compatibility surfaces from current schema, API scripts,
  tests, and docs: project payment fields, guide checklist fields, task-owned
  artifact fields, generic checker-policy version locks, wrapper methods, and
  the obsolete React proposal source document.

## Why It Changed

The manual trigger flow was useful while building the agent endpoints, but it is
not the product lifecycle. When a guide/source snapshot enters Workstream, the
system should immediately start its own setup work in the background. The
project owner should not know or call internal agent routes.

The cleanup is part of the same correction: stale request fields were making
the real API drill confusing and could reintroduce the wrong mental model.

## Design Chosen

- Celery is the durable worker boundary for project setup.
- Redis is the local broker for development.
- The HTTP request path persists the guide/source snapshot and enqueues a job;
  it does not run agents inline.
- The Celery task creates a Workstream-owned internal actor with
  `auth_source="workstream_system"` for audit provenance.
- Queue readiness is preflighted before mutation when autostart is enabled, so
  missing queue configuration does not leave half-created guide setup state.
- Queue checks are not run on read paths.
- Blocking Celery/Kombu queue checks are offloaded from the async request loop.
- If the queue fails after a guide/source snapshot has already committed, the
  durable write remains successful and the failure is logged for retry/repair.
- Human approval remains required before an effective project policy and
  deterministic pre-submit checker bundle become active.

## Alternatives Rejected

- Keep manual setup triggers as the normal path: rejected because setup must run
  automatically from guide/source capture.
- Use FastAPI background tasks: rejected because this path needs durable worker
  semantics and a product-job boundary.
- Keep compatibility aliases for removed fields: rejected because Workstream is
  still in construction and stale contracts should fail closed.
- Generate or approve policy inside the request path: rejected because agent
  setup work must be asynchronous and policy approval remains human-owned.

## Scope Control

Allowed scope is recorded in the chunk contract. The implementation changed
project setup, worker infrastructure, current migrations/tests/scripts, docs,
and the demo API client only to align with the current API contract.

No auth adapter, payment/reputation, review/revision lifecycle, blockchain, or
post-submit redesign was added.

## Product Behavior

- Creating a guide now starts automatic setup when
  `WORKSTREAM_PROJECT_SETUP_PIPELINE_AUTOSTART=true`.
- If the queue is unavailable, guide setup fails with 503 before creating guide
  or source snapshot rows.
- If enqueue fails only after the database transaction committed, the API does
  not return a false 503 for a durable write.
- Project read paths do not depend on Celery broker configuration.
- Blocking guide sufficiency stops the pipeline and creates no
  `SubmissionArtifactPolicy`.
- Passing or warning sufficiency creates a draft policy only.
- Worker-facing review decisions remain only `accept`, `needs_revision`, and
  `reject`; this chunk does not change review decisions.

## Acceptance Criteria Proof

- Celery dependency and Redis local broker added: `backend/pyproject.toml`,
  `docker-compose.yml`.
- Configuration explicit and documented: `backend/app/core/config.py`,
  `README.md`, `docs/decision_0007_async_first_execution.md`.
- Guide create snapshots and enqueues: covered by
  `test_create_guide_autostart_enqueues_without_inline_agent_execution`.
- Later source snapshot enqueues latest snapshot: covered by
  `test_create_source_snapshot_autostart_enqueues_latest_snapshot`.
- HTTP request path does not run agents inline: covered by failing-runtime test.
- Eager Celery path runs the full setup pipeline: covered by
  `test_create_guide_autostart_runs_celery_pipeline_to_draft_policy`.
- Blocked sufficiency stops before derivation: covered by
  `test_create_guide_autostart_stops_before_derivation_when_sufficiency_blocks`.
- Queue unavailable leaves no partial guide setup rows: covered by
  `test_create_guide_autostart_requires_queue_before_persisting`.
- Project reads do not require project setup queue configuration: covered by
  `test_get_project_does_not_require_project_setup_queue`.
- Late post-commit enqueue failure does not turn a durable guide/source snapshot
  create into a false 503: covered by
  `test_create_guide_returns_created_when_post_commit_enqueue_fails` and
  `test_create_source_snapshot_returns_created_when_post_commit_enqueue_fails`.
- Removed compatibility surfaces are absent from current schema: covered by
  `test_current_schema_uses_project_policy_contract`.

## Tests/Checks Run

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && .venv/bin/python -m pytest tests/test_alembic.py -q
cd backend && .venv/bin/python -m pytest tests/test_projects.py -q -k "create_guide_autostart or create_source_snapshot_autostart"
cd backend && .venv/bin/python -m pytest tests/test_projects.py -q -k "create_guide_autostart or create_source_snapshot_autostart or get_project_does_not_require_project_setup_queue or post_commit_enqueue_fails"
cd backend && .venv/bin/python -m pytest tests/test_projects.py -q -k "project_create_rejects_payment_fields or project_guide_rejects_unknown_non_contract_fields or project_guide_update_rejects_unknown_non_contract_fields or activation_uses_policy_bundle_without_guide_owned_artifact_fields"
cd backend && .venv/bin/python -m pytest tests/test_projects.py -q
npm --prefix demos/week1_api_demo_ui run build
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/test_agent_gates.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
git diff --check
```

Result summary:

- ruff: passed.
- Alembic tests: 4 passed.
- Project autostart tests before external review fixes: 5 passed.
- Focused project setup queue/autostart tests after external review fixes: 8 passed.
- Project cleanup focused tests: 7 passed.
- Full project-module suite before external review fixes: 193 passed.
- Full project-module suite after external review fixes: 196 passed.
- Demo UI build: passed.
- Markdown link, stale wording, loop memory, internal review evidence, and diff
  whitespace checks: passed.
- Static agent gate: `REVIEW_REQUIRED` for expected L1 risk/size/CI-test
  breadth; internal reviewer tracks covered it.

## Test Delta

Tests added or strengthened:

- automatic guide-create enqueue without inline agent execution;
- queue-unavailable no-partial-persist behavior;
- eager Celery full setup pipeline;
- blocked sufficiency stop before derivation;
- later source snapshot enqueue;
- current schema absence checks for discarded fields.

Tests removed or rewritten:

- compatibility/backfill migration tests for discarded construction-state fields
  were removed because no backward compatibility is being preserved.

## CI Integrity

- No GitHub workflow was changed.
- No lint/typecheck/test command was weakened.
- Backend dependency was added for Celery.
- Local Redis image is digest-pinned.
- Existing Postgres local service was not changed in this PR.

## Reviewer Results

Internal review evidence:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-08-internal-review-evidence.md`

Reviewed code SHA: `ec9810bf1408a12a9840645481619744fcbebe0f`

Reviewed at: `2026-07-05T21:46:07Z`

Reviewer run IDs: local-senior-engineering-review-20260705T214607Z, local-qa-test-review-20260705T214607Z, local-security-auth-review-20260705T214607Z, local-product-ops-review-20260705T214607Z, local-architecture-review-20260705T214607Z, local-docs-review-20260705T214607Z, local-reuse-dedup-review-20260705T214607Z, local-ci-integrity-review-20260705T214607Z, local-test-delta-review-20260705T214607Z

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Queue preflight and wrapper cleanup addressed before evidence. |
| QA/test | PASS AFTER FIXES | None | Added autostart and queue-failure coverage; full project suite passed. |
| security/auth | PASS AFTER FIXES | None | Redis pinned; system actor provenance explicit. |
| product/ops | PASS AFTER FIXES | None | Normal setup is automatic; human policy approval remains. |
| architecture | PASS AFTER FIXES | None | Celery owns the worker boundary; no lifecycle redesign. |
| CI integrity | PASS AFTER FIXES | None | No workflow weakening; dependency and compose change reviewed. |
| docs | PASS AFTER FIXES | None | Active docs updated; obsolete proposal source removed. |
| reuse/dedup | PASS AFTER FIXES | None | Existing service/compiler paths reused; redundant wrappers removed. |
| test delta | PASS AFTER FIXES | None | Removed compatibility tests replaced by current-contract assertions. |

## External Review

External review response file:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-08-external-review-response.md`

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | PASS AFTER FIXES | Addressed three actionable comments: read-path queue check, blocking queue I/O in async service, and false 503 after post-commit enqueue failure. |
| GitHub checks | Passing before follow-up push | Agent Gates, Backend, and Week 1 API Demo UI were passing before the external-review fix commit; they must rerun after push. |

## Remaining Risks

- Direct Celery enqueue after commit is semantically honest for the API caller,
  but a future durable outbox is the stronger pattern for guaranteed eventual
  enqueue after broker outages.
- Explicit setup trigger routes remain available for development and repair;
  normal project setup no longer depends on them.

## Follow-Up Work

- Open the PR and wait for external CodeRabbit/GitHub checks.
- Address external review comments in a separate external-review response file.
- After merge, resume the real Terminal Benchmark drill using the automatic
  setup path one API step at a time.

## Human Review Focus

Please inspect:

- `backend/app/modules/projects/service.py`
- `backend/app/modules/projects/setup_queue.py`
- `backend/app/workers/project_setup.py`
- `backend/alembic/versions/0002_project_guide_foundation.py`
- `backend/alembic/versions/0003_task_queue_assignment.py`
- `backend/tests/test_projects.py`
- `backend/tests/test_alembic.py`
- `docker-compose.yml`
- the removed `docs/proposal_workstream_arch_today_source.md`

## Human Merge Ownership

- The PR must not be merged until the user explicitly approves that specific PR.
