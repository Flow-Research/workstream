# Chunk Contract: WS-POL-001-13 - Task Context And Submission Requirement APIs

## Parent Initiative

`WS-POL-001` - Submission Artifact Policy Foundation

## Goal

Expose worker-safe task context, exact submission requirements, and
operator-only locked provenance through HTTP APIs.

This chunk covers APIs 8-10 only:

```text
GET /api/v1/tasks/{task_id}/work-context
GET /api/v1/tasks/{task_id}/submission-requirements
GET /api/v1/tasks/{task_id}/locked-context
```

## Why This Chunk Exists

The live API drill proved that workers can eventually pass pre-submit checks,
but the worker had to infer the exact requirements from failures. A real worker
must see the locked requirements before submitting, and operators must see full
locked provenance without using SQL.

## Risk Class

L1

## SLA

P1

## Work Type

Backend API, task lifecycle visibility, authorization, tests, docs.

## Depends On

`WS-POL-001-12`

## Allowed Files

```text
backend/app/modules/tasks/**
backend/app/modules/projects/schemas.py
backend/tests/test_tasks.py
backend/scripts/api_contract_e2e.py
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
backend/app/modules/checkers/**
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

- `work-context` and `submission-requirements` require existing task visibility
  for `admin`, `project_manager`, or the worker currently allowed to work the
  task.
- `locked-context` is operator-only for `admin` or `project_manager`.
- Persisted actor profiles do not grant route authorization. Token-derived role
  checks remain the route gate.

## Acceptance Criteria

- `work-context` returns the task, project/guide summary, active locked guide
  content, review/revision/payment summary, and worker-facing lifecycle state.
- `submission-requirements` returns exact required artifacts, required evidence
  keys/labels/descriptions, forbidden artifact rules, allowed storage schemes,
  packaging rules, hash algorithm, storage reference rules, and required
  attestation concepts from the task's locked effective project policy.
- Worker-facing responses omit raw compiled checker bundles, checker configs,
  internal route tokens, private source refs, full source snapshot hashes,
  Celery task ids, and internal setup errors.
- `locked-context` returns full operator provenance: guide source snapshot
  id/hash, effective policy id/hash, pre-submit checker policy id/hash,
  post-submit checker policy id/hash/body summary, review policy version,
  and revision policy version. Compensation is not guide or checker context;
  its frozen version is read from `TaskAssignment` or `ReviewLease` through the
  owning WS-CON surface.
- All task context APIs read already-stamped task locked context. They must not
  recompute policy from the current active guide or current project policy.
- If required locked context is missing or inconsistent, task context endpoints
  fail closed with a structured setup/locked-context error.
- Tests prove guide v2 activation does not silently change work-context or
  submission requirements for a task already locked to v1.

## Verification Commands

```bash
cd backend && .venv/bin/pytest tests/test_tasks.py
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py
python scripts/check_internal_review_evidence.py
```

Also run:

```bash
rg -n "task binding|task-owned policy|direct DB|DB inspection" docs backend examples .agent-loop
```

## Required Reviewers

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

## Human Review Focus

Whether worker-facing requirements are complete enough for a real submitter
without exposing internal compiler authority.

## Stop Conditions

- Stop if worker-facing requirements require raw compiled checker bundles to be
  useful.
- Stop if route authorization cannot distinguish worker-safe context from
  operator-only locked provenance.
- Stop if task context would need to recompute from the current guide instead
  of reading stamped locked context.
