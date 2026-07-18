# Chunk 4: Task Queue And Assignment

## Scope

This chunk adds the first task queue backend module.

It covers:

- task records under active projects
- locked guide and policy context during task screening before release to `READY`
- worker actor profile records
- reviewer actor profile records
- assignment records
- lifecycle guards from `DRAFT` through `IN_PROGRESS`
- audit events for task status changes
- skill tags on tasks and actor profiles

## Non-Scope

This chunk does not implement:

- submission packets
- evidence items
- artifact storage
- checker runs
- human review decisions
- revision replay execution
- contribution records
- payment execution
- reputation calculation
- frontend screens

## Expected Modules

- `backend/app/modules/tasks/models.py`
- `backend/app/modules/tasks/repository.py`
- `backend/app/modules/tasks/schemas.py`
- `backend/app/modules/tasks/service.py`
- `backend/app/modules/tasks/router.py`
- `backend/app/modules/tasks/lifecycle.py`
- `backend/alembic/versions/0003_task_queue_assignment.py`
- `backend/tests/test_tasks.py`

Shared wiring:

- `backend/app/db/models.py`
- `backend/app/api/router.py`

## Data Model Impact

Current tables after `WS-POL-001-11`:

- `actor_identities`
- `actor_profiles`
- `workstream_tasks`
- `task_assignments`
- `audit_events`

Note: `WS-POL-001-11` supersedes the separate worker/reviewer profile storage
from this earlier chunk. Worker and reviewer profile behavior moves to the
shared `ActorProfile` model, while task assignment and audit records keep using
stable actor ids.

Task records store:

- project id
- locked guide version
- locked guide source snapshot id/hash
- locked effective project submission artifact policy hash
- locked pre-submit checker bundle hash
- locked post-submit checker policy version
- locked review policy version
- locked revision policy version
- locked payment policy version
- task source metadata
- task content fields
- skill tags
- base amount, currency, and payout type
- current lifecycle status
- assigned worker id

Assignments enforce one active worker per task in v0.1. Project policies that allow multiple workers are later work.

Audit events store actor-attributed status changes with Flow subject, issuer, roles, claim snapshot, auth source, dev-auth marker, transition reason, and structured event payload containing locked guide/policy context or assignment identifiers where relevant.

## API Impact

New endpoints:

- `POST /api/v1/projects/{project_id}/tasks`
- `GET /api/v1/tasks/{task_id}`
- `POST /api/v1/tasks/{task_id}/screen`
- `POST /api/v1/tasks/{task_id}/release`
- `POST /api/v1/tasks/{task_id}/claim`
- `POST /api/v1/tasks/{task_id}/start`
- `GET /api/v1/tasks/{task_id}/audit-events`
- `POST /api/v1/workers/me/profile`

Routers stay thin. Services own authorization, lifecycle checks, locked context stamping, assignment rules, and audit writes.

## Lifecycle Impact

Implemented transitions:

```text
DRAFT -> SCREENING
SCREENING -> READY
READY -> CLAIMED
CLAIMED -> IN_PROGRESS
```

Rules:

- `DRAFT -> SCREENING` requires active project guide context and complete task source, description, acceptance, and rejection fields, then locks guide and policy versions on the task.
- `SCREENING -> READY` requires that guide, checker, review, revision, and payment policy context be locked.
- `READY -> CLAIMED` creates an active assignment and blocks a second active assignment.
- `CLAIMED -> IN_PROGRESS` requires an active assignment for the actor or an authorized operator role.
- every status change writes an audit event.

## Security/Auth Impact

Workstream still verifies external Flow actor context only. It does not add login, signup, password reset, password storage, or primary auth sessions.

Role expectations:

- admin and project manager can create, screen, release, and inspect tasks
- workers can claim ready tasks only when an active worker profile already exists
- workers create or refresh their own active profile through
  `POST /api/v1/workers/me/profile` before claim; identity fields come from the
  verified Flow token and the request may only supply normalized skill tags
- worker claim does not self-create or overwrite worker eligibility skill state
- workers can read ready tasks and their own assigned tasks
- admins and project managers can start a claimed task for operational testing, but do not create worker assignments for themselves through the claim path
- non-assigned operator starts require a non-empty override reason in audit
- audit API responses redact persisted claim snapshots unless a later privileged endpoint explicitly exposes them
- audit events persist the actor audit context from the verified token

## Tests Required

- migration upgrade/downgrade includes Chunk 4 tables
- task model metadata includes one-active-assignment constraint
- task can be created in `draft`
- task cannot enter `screening` without required fields
- task enters `ready` only after guide and policy context are locked
- task can move `ready -> claimed -> in_progress`
- second claim is rejected while an active assignment exists
- status transitions write actor-attributed audit events
- unauthorized actors are rejected for project-manager actions

## Conditions Of Satisfaction

- backend tests pass against Postgres
- docstring coverage remains above threshold
- stale wording scan passes for docs changed in this chunk
- Markdown link check passes for docs changed in this chunk
- senior engineering, QA/test, and security/auth verification complete or concerns are recorded for operator review

## Reviewer Agents Required

- senior engineering
- QA/test
- security/auth
