# PR Trust Bundle: WS-POL-001-06

## Chunk

`WS-POL-001-06` - Terminal Benchmark Real Fixture Drill

## Goal

Use a real Terminal Benchmark reference fixture as an external-project proof for
the current Workstream setup-agent, project policy-bundle, task locked-context,
pre-submit, post-submit checker, and revision resubmission lifecycle.

This pass also cleans up stale construction-state product contracts before
continuing pre-submit checker work.

## Human-Approved Intent

The user explicitly pushed back that:

- project creation must be shell-only;
- base amount, currency, and payout terms belong to `PaymentPolicy`;
- `ProjectGuide` is human-facing guide material, not a machine-readable
  artifact checklist;
- stale `evidence_policy` and guide checklist fields should be removed, not
  preserved through compatibility aliases;
- request bodies must hard-fail unknown fields;
- Terminal Benchmark is a real external-project proof harness, not Workstream
  product runtime.

## What Changed

- Added `0010_remove_legacy_project_guide_fields.py`.
- Removed project-owned `base_amount` and `currency` columns from the current
  project shape.
- Removed legacy structured guide fields from current project guide model/API
  shape, including `required_task_fields`, `required_submission_fields`,
  `reviewer_rubric`, `forbidden_actions`, `evidence_policy`, and related
  checklist fields.
- Preserved `approved_by` and `effective_at` as server-written guide activation
  provenance and exposes them on read responses.
- Kept `approved_by` and `effective_at` forbidden in create/update request
  bodies.
- Made `0010` fail closed when existing `guide_source_snapshots` are present,
  forcing stale setup data to be rebuilt under the current guide-source
  contract.
- Updated task screening so it validates task-owned contract fields, not
  guide-side required fields.
- Updated active docs/templates/roadmaps so payment terms are policy-owned and
  task-visible payout fields are locked snapshots from `PaymentPolicy`.
- Updated the Terminal Benchmark example to require the OpenAI Agents SDK
  adapter and real Terminal Benchmark reference project guide, reviewer program, task TOML, and
  review packet material.
- Removed Terminal Benchmark-specific derivation shortcuts from the local
  fixture adapter.
- Updated the CI-invoked Week 1 real API drill so it uses the current request
  contracts: shell project creation, payment terms only under `PaymentPolicy`,
  human-facing guide content plus policy records, and no task
  `required_files`/`required_evidence` intake-policy inputs.
- Addressed CodeRabbit review feedback by clarifying the fail-closed migration
  guard, aligning the `ProjectGuide` field list with the ORM model, removing
  dead task-validation map entries, and bounding Terminal Benchmark
  reviewer-root discovery.
- Updated tests for request hard gates, activation provenance, migration schema
  cleanup, stale snapshot fail-closed behavior, task/checker behavior, and the
  example contract.

## Design Chosen

The current v0.1 contract is:

```text
Project = shell metadata
ProjectGuide = human-facing guide material
PaymentPolicy = base amount, currency, payout type, payout rules
SubmissionArtifactPolicy = machine-readable artifact intake contract
Project PreSubmitCheckerPolicy = compiled deterministic pre-submit bundle
Task = locks guide/source/policy/checker/payment context during screening
```

There is no compatibility alias for `ProjectGuide.evidence_policy` or guide-side
required fields. Existing pre-production setup data with guide-source snapshots
must be rebuilt instead of silently carrying stale provenance through a
destructive cleanup.

## Alternatives Rejected

- Keep project `base_amount` / `currency`: rejected because payment belongs to
  `PaymentPolicy`.
- Preserve guide checklist fields as compatibility aliases: rejected because
  those fields were construction-state shortcuts and would keep the wrong
  mental model alive.
- Let old guide-source snapshots survive cleanup: rejected because those hashes
  may have been calculated from now-deleted guide fields.
- Generate Terminal Benchmark-specific backend logic: rejected because the
  example must not become product runtime.
- Let the Terminal Benchmark example fall back to `local_fixture`: rejected
  because this proof is meant to exercise the setup-agent route.

## Scope

Runtime/backend:

- `backend/alembic/versions/0010_remove_legacy_project_guide_fields.py`
- `backend/app/adapters/project_agents/local_fixture.py`
- `backend/app/modules/projects/models.py`
- `backend/app/modules/projects/schemas.py`
- `backend/app/modules/projects/service.py`
- `backend/app/modules/tasks/service.py`

Tests:

- `backend/tests/test_alembic.py`
- `backend/tests/test_checkers.py`
- `backend/tests/test_projects.py`
- `backend/tests/test_tasks.py`
- `backend/scripts/week1_api_e2e.py`

Docs/examples/process:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**`
- `README.md`
- `docs/architecture_data_model.md`
- `docs/architecture_lockdown.md`
- `docs/architecture_system_architecture.md`
- `docs/operations_operator_workflow.md`
- `docs/operations_project_operating_manual.md`
- `docs/operations_queue_policy.md`
- `docs/operations_reviewer_workflow.md`
- `docs/product_first_user_flows.md`
- `docs/roadmap_implementation_backlog.md`
- `docs/spec_chunk_3_project_guide_foundation.md`
- `docs/spec_chunk_4_task_queue_assignment.md`
- `docs/template_project_guide.md`
- `docs/template_task.md`
- `examples/terminal_benchmark/**`

## Product Behavior

- Project create rejects `base_amount` and `currency`.
- Project guide create/update rejects legacy guide checklist fields and
  server-written activation provenance fields.
- Active guide responses expose `approved_by` and `effective_at`.
- Guide activation still requires complete payment policy context.
- Task screening stamps payout values from locked payment policy context.
- Pre-submit failure remains pre-submit feedback / `pre_submission_checker_failed`;
  it does not create a submission and does not become `needs_revision`.
- Post-submit checker failure can route a valid immutable submission to
  `needs_revision`.
- Fixed v2 submission supersedes v1 and can return to `review_pending`.

## Verification

Passed locally:

```bash
git diff --check
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
cd backend && uv run ruff check app tests ../examples/terminal_benchmark/terminal_benchmark_api_e2e.py
cd backend && uv run pytest tests/test_alembic.py -q
cd backend && uv run pytest tests/test_checkers.py -q
cd backend && uv run pytest tests/test_tasks.py -q
cd backend && uv run pytest tests/test_projects.py -q
cd backend && WORKSTREAM_DATABASE_URL=<local-test-db-url> uv run python scripts/week1_api_e2e.py
cd backend && .venv/bin/python -m ruff check app tests scripts ../examples/terminal_benchmark/terminal_benchmark_api_e2e.py
cd backend && .venv/bin/python -m pytest tests/test_alembic.py -q
cd backend && .venv/bin/python -m pytest tests/test_tasks.py -k 'screen or missing or required or locked_context' -q
```

Results:

- `tests/test_alembic.py`: 6 passed
- `tests/test_checkers.py`: 47 passed
- `tests/test_tasks.py`: 60 passed
- `tests/test_projects.py`: 188 passed
- `scripts/week1_api_e2e.py`: passed against local Postgres on 2026-07-05
- CodeRabbit fix validation:
  - ruff: passed
  - `tests/test_alembic.py`: 6 passed
  - targeted task screening/locked-context subset: 11 passed, 49 deselected

## Internal Review

Evidence:

`.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-06-internal-review-evidence.md`

Reviewed implementation SHA:

`96792961c7cb74f31150df803c533fe4c6432636`

Reviewer summary:

- senior engineering: PASS
- QA/test: PASS WITH LOW RISKS
- security/auth: PASS WITH LOW RISKS
- product/ops: PASS
- architecture: PASS
- docs: PASS WITH LOW RISKS
- reuse/dedup: PASS WITH LOW RISKS
- test delta: PASS WITH LOW RISKS
- CI integrity: PASS AFTER FIXES

## External Review

External GitHub Actions and CodeRabbit must rerun after this evidence/status
commit is pushed. Do not treat the previous PR check state as current for the
new commits.

## Remaining Risks

- The Terminal Benchmark drill is local proof harness code, not CI-required
  runtime.
- The live OpenAI Agents SDK drill requires ignored local credentials and model
  configuration.
- The migration intentionally blocks databases that already contain
  `guide_source_snapshots`; any such local pre-production data must be rebuilt
  through the current policy-bundle path.

## Human Review Focus

- Confirm project creation is shell-only.
- Confirm payment terms live in `PaymentPolicy`.
- Confirm `ProjectGuide` is now human-facing guide material only.
- Confirm request bodies fail closed for unknown/stale fields.
- Confirm `0010` intentionally fails closed for old snapshot provenance.
- Confirm Terminal Benchmark remains example proof only.
- Confirm external checks rerun on the pushed commits before merge.

## Human Merge Ownership

Only the user can approve and merge the PR. The agent must not merge without
explicit user approval for that specific PR.
