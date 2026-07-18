# Chunk Contract: WS-POL-001-12 - Project Setup And Policy Visibility APIs

## Parent Initiative

`WS-POL-001` - Submission Artifact Policy Foundation

## Goal

Expose project setup and project policy state through authorized HTTP APIs so
operators no longer inspect Postgres to continue a real setup drill.

This chunk covers APIs 1-7 only:

```text
GET /api/v1/projects/{project_id}/guides/{guide_id}/setup-runs/latest
GET /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports
GET /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}
GET /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies
GET /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}
GET /api/v1/projects/{project_id}/guides/{guide_id}/effective-submission-artifact-policy
GET /api/v1/projects/{project_id}/guides/{guide_id}/pre-submit-checker-policy
```

## Why This Chunk Exists

The Terminal Benchmark live API drill proved that automatic setup works, but
the drill still needed direct DB reads to find setup outputs. That is not an
acceptable operator or demo path.

## Risk Class

L1

## SLA

P1

## Work Type

Backend API, project setup persistence, project policy visibility, tests, docs.

## Allowed Files

```text
backend/alembic/versions/**
backend/app/db/models.py
backend/app/modules/projects/**
backend/app/workers/project_setup.py
backend/tests/test_projects.py
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
backend/app/modules/tasks/**
backend/app/modules/checkers/**
Workstream-owned login, signup, password reset, password storage, primary auth sessions, or API-key auth
Flow token verifier replacement
frontend/demo UI work
payment/reputation/blockchain settlement
agent prompt redesign or new project setup agent behavior
unrestricted generated checker code
review decision token changes
project owner-authored SubmissionArtifactPolicy schema
DB-only drill steps as accepted proof
```

## Authorization Contract

- All endpoints require verified token auth.
- All endpoints require project setup operator access: `admin` or
  `project_manager`.
- Worker, reviewer, finance, and auditor roles do not receive these project
  setup endpoints in v0.1.

## Acceptance Criteria

- `ProjectSetupRun` persistence exists for automatic project setup jobs.
- `ProjectSetupRun` is a non-authoritative orchestration ledger. It references
  downstream truth by id/hash but does not replace sufficiency report, policy,
  effective policy, or pre-submit checker policy records.
- Creating a guide/source snapshot with automatic setup enabled creates a setup
  run before enqueue.
- Successful enqueue records the Celery task id.
- Enqueue failure records `enqueue_failed` with a bounded error summary.
- The project setup worker updates setup-run status and current step as it runs
  guide sufficiency and policy derivation.
- Setup-run statuses are explicit: `queued`, `enqueue_failed`,
  `running_sufficiency_agent`, `sufficiency_blocked`,
  `running_policy_derivation_agent`, `policy_draft_ready`, `setup_blocked`,
  and `failed`.
- `GET .../setup-runs/latest` returns the latest setup run scoped to the
  requested project and guide with source snapshot id/hash, Celery task id,
  status, current step, output ids, bounded error code/summary, and timestamps.
- Setup-run errors do not expose signed URLs, credential-bearing refs,
  token-bearing refs, local filesystem paths, private object keys, or raw stack
  traces.
- Sufficiency report list/get endpoints return only reports for the requested
  project and guide.
- Submission artifact policy list/get endpoints return only policies for the
  requested project and guide.
- Effective policy GET returns the current approved effective project
  submission artifact policy for the guide/source snapshot.
- Pre-submit checker policy GET returns the current compiled project
  `PreSubmitCheckerPolicy` summary for the guide/effective policy.
- The pre-submit checker policy response can include checker names, compiler
  version, compiled bundle hash, lifecycle status, source snapshot id/hash, and
  effective policy id/hash. It must not expose mutable authority beyond the
  persisted compiled bundle summary.

## Verification Commands

```bash
cd backend && .venv/bin/pytest tests/test_projects.py
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py
python scripts/check_internal_review_evidence.py
```

Also run:

```bash
rg -n "DB inspection|direct DB|setup-runs/latest|ProjectSetupRun" docs backend examples .agent-loop
```

## Required Reviewers

senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta.

## Human Review Focus

Setup-run status names, project setup operator access, redaction, and keeping
`ProjectSetupRun` as a ledger rather than a policy source of truth.

## Stop Conditions

- Stop if durable setup-run persistence requires a broader queue/outbox
  redesign.
- Stop if project policy visibility would require exposing raw compiled checker
  authority to non-operator actors.
- Stop if setup-run errors cannot be safely redacted.
