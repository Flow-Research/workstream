# Internal Review Evidence: WS-POL-001-06

## Chunk

WS-POL-001-06

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 49101d4ad3fc22ec6e6065b1e593ef04145db953

Reviewed at: 2026-07-09T06:13:59Z

Reviewer run IDs: senior-engineering-final-reviewer-run-id, qa-test-final-reviewer-run-id, security-auth-final-reviewer-run-id, product-ops-final-reviewer-run-id, architecture-final-reviewer-run-id, docs-final-reviewer-run-id, reuse-dedup-final-reviewer-run-id, test-delta-final-reviewer-run-id, ci-integrity-final-reviewer-run-id

Current privacy-scrub chunk: `WS-POL-001-16-terminal-benchmark-live-api-drill`.
This file was touched only to remove private/local Terminal Benchmark source
identifiers from older public evidence. The original `WS-POL-001-06` review
provenance is retained below for historical context.

Original reviewed revision:

Reviewed code SHA: 96792961c7cb74f31150df803c533fe4c6432636

Reviewed at: 2026-07-05T13:59:55Z

Reviewer run IDs: reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id, reviewer-run-id

## Reviewed Change

Branch: `codex/ws-pol-001-06-terminal-benchmark-drill`

Scope:

- `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**`
- `README.md`
- `backend/alembic/versions/0010_remove_legacy_project_guide_fields.py`
- `backend/app/adapters/project_agents/local_fixture.py`
- `backend/app/modules/projects/models.py`
- `backend/app/modules/projects/schemas.py`
- `backend/app/modules/projects/service.py`
- `backend/app/modules/tasks/service.py`
- `backend/tests/test_alembic.py`
- `backend/tests/test_checkers.py`
- `backend/tests/test_projects.py`
- `backend/tests/test_tasks.py`
- `backend/scripts/week1_api_e2e.py`
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

The chunk now does two things in one approved scope: keeps the Terminal
Benchmark fixture drill as example proof material, and removes stale
construction-state product contracts before continuing pre-submit checker work.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Confirmed CodeRabbit fixes are minimal and preserve intended behavior. |
| qa/test | PASS WITH LOW RISKS | None | Confirmed migration guard, task validation cleanup, fixture-root bound, and docs field list; wording precision was tightened before commit. |
| security/auth | PASS WITH LOW RISKS | None | Confirmed fail-closed migration guard, bounded fixture traversal, no auth/payment weakening, and no normal-path secret/path leakage. |
| product/ops | PASS | None | Confirmed project creation, payment policy ownership, worker/reviewer status semantics, and naming remain aligned. |
| architecture | PASS | None | Confirmed project-scoped policy architecture is preserved and no compatibility alias is introduced. |
| docs | PASS WITH LOW RISKS | None | Confirmed docs are accurate; evidence/status are refreshed in this commit. |
| reuse/dedup | PASS WITH LOW RISKS | None | Confirmed no missed helper or redundant abstraction in the CodeRabbit fix set. |
| test delta | PASS WITH LOW RISKS | None | Confirmed tests were not weakened; Alembic guard test still seeds a pre-cleanup snapshot and asserts failure. |
| ci integrity | PASS AFTER FIXES | None | Found stale evidence after CodeRabbit fixes; this evidence/status update binds the new reviewed SHA. |

## Valid Findings Addressed

- Tracked and tested `0010_remove_legacy_project_guide_fields.py`.
- Removed project-owned payment fields from the current project model/API.
- Kept `base_amount`, `currency`, and payout terms under `PaymentPolicy`.
- Removed legacy structured guide request/response/model fields, including
  `evidence_policy`, guide-side required fields, guide rubrics, and guide
  checklist aliases.
- Preserved `ProjectGuide.approved_by` and `effective_at` as server-written
  activation provenance and restored them to read responses.
- Kept `approved_by` and `effective_at` forbidden in create/update request bodies.
- Made the cleanup migration fail closed when old `guide_source_snapshots`
  exist, so stale snapshot provenance cannot survive the destructive cleanup.
- Stopped task screening from reading guide-side `required_task_fields`.
- Reworded active docs so task screening uses task-owned contract fields and
  locked policy context.
- Reworded operator, reviewer, architecture, roadmap, project-guide, and task
  docs so payment terms are policy-owned and task payout values are locked
  snapshots.
- Removed Terminal Benchmark-specific branching from the local fixture adapter.
- Updated the Terminal Benchmark example to require the OpenAI Agents SDK
  adapter and real Terminal Benchmark reference project guide, reviewer program, task TOML, and
  review packet material.
- Updated `WS-POL-001-06` chunk scope and master chunk map to include the
  intentional docs and migration cleanup.
- Updated the Week 1 real API E2E script after GitHub Actions proved it still
  sent stale request bodies. The script now creates a shell project, keeps
  payment terms in `PaymentPolicy`, sends only human-facing guide content plus
  policy records for guide creation, and no longer sends task
  `required_files`/`required_evidence` as intake-policy inputs.
- Narrowly expanded the `WS-POL-001-06` contract to allow
  `backend/scripts/week1_api_e2e.py` because that script is the CI-invoked
  real API drill for the corrected request-body contract.
- Addressed CodeRabbit review feedback:
  - clarified the `0010_guide_cleanup` guard as a fail-closed check for any
    existing guide-source snapshots before the destructive guide-field cleanup;
  - added missing `ProjectGuide.status` and `ProjectGuide.updated_at` to the
    data-model field list;
  - removed unused task validation map entries left from guide-driven
    validation;
  - bounded Terminal Benchmark reviewer-root discovery to the fixture root and
    immediate parent unless the explicit reviewer-root environment variable is
    set.

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

Focused suites also passed during the repair loop:

- project payment-field rejection and legacy guide-field rejection
- guide activation provenance readback
- guide cleanup migration and stale snapshot fail-closed guard

## External Review Status

External GitHub Actions and CodeRabbit must rerun after this evidence/status
commit is pushed. This internal evidence does not replace external review.
