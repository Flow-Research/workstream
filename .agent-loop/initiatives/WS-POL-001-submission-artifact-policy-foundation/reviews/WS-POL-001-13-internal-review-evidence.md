# Internal Review Evidence: WS-POL-001-13

## Chunk

WS-POL-001-13

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: f533f1a572a38d4e8ecd34ff6316885c6c6b1016

Reviewed at: 2026-07-08T02:09:55Z

Reviewer run IDs: senior-engineering-final-019f3ecb-6123-7581-9b08-a1812b789d57, qa-test-final-019f3ecb-a018-7e02-81a7-3a7fd102a4ba, security-auth-final-019f3ecb-d5a9-7800-94b3-e4358974f0cd, product-ops-final-019f3ecc-0e2d-7e90-873a-af311a10fd59, architecture-final-019f3ecc-5034-7da0-a53e-1cb66880535b, docs-final-019f3ecc-87cf-75a3-b806-d694cf0f8114, reuse-dedup-final-019f3ed0-bdf1-7ae3-99ae-a33db36dea1c, test-delta-final-019f3ed0-f9d9-7590-a829-de92b9296105, senior-engineering-external-019f3f6d-441f-7340-9bcc-ef92155d956d, qa-test-external-019f3f6d-4986-7612-a7a7-9457a2182d0b, security-auth-external-019f3f6d-4fea-7890-a372-a261d2482b91, product-ops-external-019f3f6d-5758-79d3-a7d4-3d58933064da, docs-external-final-019f3f76-dd39-74f3-8cf3-d551908fa058, test-delta-external-019f3f6d-685a-7300-82ab-966c3c034976

After the reviewed SHA, only evidence files changed.

## Reviewed Change

Scope:

- Adds `GET /api/v1/tasks/{task_id}/work-context` for worker-safe task, project, guide, payment, review/revision version, and lifecycle context.
- Adds `GET /api/v1/tasks/{task_id}/submission-requirements` for exact locked submission packet fields, artifacts, evidence, storage rules, packaging, hash algorithm, and attestation terms.
- Adds `GET /api/v1/tasks/{task_id}/locked-context` for `admin` and `project_manager` locked provenance.
- Validates task-stamped guide source snapshot, effective project policy, project pre-submit checker, post-submit checker, review, revision, and payment context before response projection.
- Keeps worker-facing responses free of private source/import refs, assignment provenance, raw compiled bundles, checker configs, setup internals, source snapshot hashes, and policy provenance hashes.
- Redacts existing worker-visible `GET /tasks/{task_id}` responses so workers cannot bypass `work-context` redaction.
- Fails closed with structured `task_locked_context_invalid` when locked context is missing, stale, hash-mismatched, or hash-consistent but malformed.
- Extends the real API contract drill to call the three task-context APIs through HTTP.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Confirmed router/service boundaries, route-specific domain schemas, fail-closed malformed policy behavior, and worker redaction. |
| QA/test | PASS | None | Confirmed acceptance criteria, exact requirements including `package_hash`, v1 lock after v2 activation, and live API drill coverage. |
| security/auth | PASS WITH LOW RISKS | None | Confirmed no private values/hashes/configs leak. Low residual risk: worker-facing structured errors include internal field names without values. |
| product/ops | PASS | None | Confirmed worker and operator workflows, existing task read redaction, and no payment/reputation behavior expansion. |
| architecture | PASS | None | Confirmed stamped-context reads, no current-guide recompute, operator-only locked context, and allowed-file scope. |
| docs | PASS | None | Confirmed glossary, architecture, operations, and roadmap docs align with the new API surfaces. |
| reuse/dedup | PASS WITH LOW RISKS | None | Low residual risk: required packet field constants mirror `SubmissionCreate`; future shared extraction can avoid drift. |
| test delta | PASS WITH LOW RISKS | None | Confirmed strengthened tests and no skips/removals. Low residual risk: locked-context response shape is sampled rather than fully enumerated. |

## Valid Findings Addressed

- Replaced broad worker `TaskResponse` usage in `work-context` with `TaskWorkerTaskContext`.
- Removed private source/import/creator/assignment fields from worker `work-context` task data.
- Stopped exposing mutable same-version review/revision/payment row details in worker work context; response now uses stamped guide/payment values and guide-version references.
- Added route-specific domain error schemas so submission creation documents only `pre_submission_checker_failed` and task-context endpoints document only `task_locked_context_invalid`.
- Added `package_hash` to the exact worker-facing required packet field list.
- Removed `forbidden_artifacts.source` from worker-facing submission requirements.
- Redacted private source/import/creator/assignment fields from existing worker-visible `GET /tasks/{task_id}` responses.
- Added explicit locked effective-policy projection validation so malformed hash-consistent policy shapes return structured `task_locked_context_invalid`.
- Centralized locked-context required fields and reused the shared missing-field helper.
- Added tests for worker-safe redaction, operator-only locked context, exact submission requirements, malformed policy fail-closed behavior, same-version policy mutation, and v1 locked context after v2 guide activation.
- Updated the real API contract drill to call `work-context`, `submission-requirements`, and `locked-context`.
- Addressed CodeRabbit's test-maintainability nitpick by capturing the compiled
  bundle before deleting the ORM row in the malformed locked-context
  regression.

## Commands Run

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
rg -n "task binding|task-owned policy|direct DB|DB inspection" docs backend examples .agent-loop
cd backend && .venv/bin/pytest tests/test_tasks.py::test_worker_task_response_redacts_locked_policy_hashes tests/test_tasks.py::test_assigned_worker_submits_v1_and_task_moves_to_submitted tests/test_tasks.py::test_task_context_apis_return_worker_requirements_and_operator_provenance tests/test_tasks.py::test_submission_requirements_fail_closed_on_hash_consistent_malformed_policy_shape -q
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py
cd backend && .venv/bin/pytest tests/test_tasks.py
```

Results:

- Ruff: passed.
- Stale wording scan: passed.
- Markdown link check: passed for 7 changed Markdown files.
- Diff whitespace check: passed.
- Stale model/no-DB scan: expected references only in chunk contracts, status/decision docs, and the documented future no-DB proof path; no active per-task policy wording was found.
- Focused task context and worker redaction regressions: 4 passed in 43.18s.
- API contract real API E2E: passed and called `work-context`, `submission-requirements`, and `locked-context` through HTTP.
- Full task suite: 81 passed in 743.67s.

## Remaining Risks

- Worker-facing locked-context errors include internal field names such as locked context field identifiers. They do not expose values, hashes, private refs, compiled bundles, checker configs, or source material. A future UX/security hardening pass can map worker errors to public categories while preserving exact operator diagnostics.
- `SUBMISSION_CREATE_REQUIRED_PACKET_FIELDS` mirrors `SubmissionCreate` required fields. It is centralized for this projection, but a future cleanup can derive it from schema metadata or move the contract beside the schema to reduce drift.
- The task context loader repeats some locked pre-submit validation concepts also used by checker execution. The current direction is acceptable because this API needs task-specific domain errors and richer context; if another reader appears, extract a shared locked-context validator.
- The next Terminal Benchmark no-DB drill is still assigned to `WS-POL-001-14`.
