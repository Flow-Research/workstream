# Chunk Contract: WS-POL-001-14 - Submission Finalize And No-DB Drill Proof

## Parent Initiative

`WS-POL-001` - Submission Artifact Policy Foundation

## Goal

Replace the public submission `lock` route with `finalize`, clarify system
actor audit semantics, and prove the full Terminal Benchmark drill through
HTTP only.

This chunk covers APIs 11-14:

```text
POST /api/v1/submissions/{submission_id}/finalize
GET  /api/v1/submissions/{submission_id}/checker-runs
GET  /api/v1/checker-runs/{checker_run_id}
GET  /api/v1/tasks/{task_id}/audit-events
```

The existing `POST /api/v1/tasks/{task_id}/submission-precheck` remains part of
the no-DB drill proof.

## Why This Chunk Exists

The live drill exposed that `/lock` is bad public wording and that the
pre-review gate needs clear system actor provenance. After APIs 1-10 exist, the
final proof must use all required state through HTTP rather than DB reads.

## Risk Class

L1

## SLA

P1

## Work Type

Backend API, submission lifecycle, checker/audit proof, tests, real API drill.

## Depends On

`WS-POL-001-13`

## Allowed Files

```text
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/tests/test_tasks.py
backend/tests/test_checkers.py
backend/scripts/api_contract_e2e.py
examples/terminal_benchmark/terminal_benchmark_api_e2e.py
docs/architecture_data_model.md
docs/architecture_system_architecture.md
docs/glossary.md
docs/operations_project_operating_manual.md
docs/roadmap_status.md
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

## Not Allowed

```text
backend/alembic/versions/**
backend/app/modules/projects/**
backend/app/workers/project_setup.py
Workstream-owned login, signup, password reset, password storage, primary auth sessions, or API-key auth
Flow token verifier replacement
frontend/demo UI work
payment/reputation/blockchain settlement
agent prompt redesign or new project setup agent behavior
review decision token changes
DB-only drill steps as accepted proof
```

## Authorization Contract

- `finalize` requires verified `admin` or `project_manager`.
- The requester must be authorized against the submission's project/task.
- The internal pre-review gate system actor cannot authorize HTTP requests and
  cannot be supplied by the client.
- Checker-run and audit reads retain their existing route permissions unless a
  test proves a visibility mismatch.

## Acceptance Criteria

- Public `POST /submissions/{submission_id}/finalize` replaces public
  `POST /submissions/{submission_id}/lock` in code, tests, scripts, examples,
  and docs. No v0.1 compatibility alias is kept.
- `finalize` is idempotent for the latest submitted version and returns the
  existing finalized response on repeat calls.
- `finalize` fails for non-latest submission versions, unfinished submissions,
  unauthorized roles, and submissions whose task locked context is missing or
  inconsistent.
- Persistence may keep `locked_at` as the internal timestamp field.
- Public audit event wording uses `submission_finalized` for the requester
  handoff. Old public `submission_locked` wording is removed from current docs,
  scripts, and tests.
- Pre-review checker execution is audited under
  `workstream-system:pre-review-gate` and includes requester actor id, issuer,
  subject, and auth source in the event payload.
- Existing checker-run list/get endpoints remain stable and expose durable
  post-submit checker results for the finalized submission.
- Existing task audit-event endpoint remains stable and exposes the finalization
  and pre-review gate path.
- The Terminal Benchmark drill proceeds from guide creation through
  `review_pending` using HTTP API responses only. Direct DB reads are allowed
  only for test setup/cleanup and migration reset, not for proving lifecycle
  state or finding ids.
- The drill explicitly proves both paths: pre-submit preflight failure returns
  `200 PreSubmitCheckResponse` with `eligible_to_submit: false`, and blocked
  submission creation returns `pre_submission_checker_failed` without creating
  a submission.

## Verification Commands

```bash
cd backend && .venv/bin/pytest tests/test_tasks.py tests/test_checkers.py
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python ../examples/terminal_benchmark/terminal_benchmark_api_e2e.py
python scripts/check_internal_review_evidence.py
```

Also run:

```bash
rg -n "/submissions/.*/lock|submission_locked|lock endpoint|DB inspection|direct DB" docs backend examples .agent-loop
```

## Required Reviewers

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

## Human Review Focus

Public `finalize` wording, operator-only authorization, system actor audit
provenance, and whether the live drill is genuinely API-only.

## Stop Conditions

- Stop if replacing public `/lock` breaks unrelated lifecycle contracts.
- Stop if system actor provenance cannot be separated from requester
  authorization.
- Stop if the Terminal Benchmark drill still requires DB inspection to prove
  lifecycle state.
