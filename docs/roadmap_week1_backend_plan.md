# Week 1 Backend Plan

## Purpose

This is the implementation plan for the June 2-5 foundation work.

The week is backend-first. Frontend work starts after the backend contract, state guards, and first workflow are stable enough to support an internal operations UI.

## Architecture Rule

Workstream v0.1 is a modular monolith.

The backend must keep clear boundaries:

- routers handle HTTP only
- Pydantic schemas define API input and output contracts
- services own workflow and business rules
- repositories own database queries
- interfaces define external boundaries
- adapters implement external boundaries
- domain/state helpers own lifecycle rules
- audit writes happen through one audit path

The stack is:

- Python
- FastAPI
- SQLAlchemy 2.x async
- Alembic
- Pydantic schemas
- Postgres
- local filesystem storage behind an object-storage interface
- external Flow authentication token verification behind an auth interface

Workstream does not own login, signup, password reset, or password storage. It verifies Flow-issued authentication tokens and derives the current actor from trusted token claims.

## Chunk Review Rule

Each implementation chunk needs a short specification before code starts.

Each chunk specification must include:

- scope
- non-scope
- files or modules expected to change
- data model impact
- API impact
- lifecycle/state impact
- security/auth impact
- tests required
- conditions of satisfaction
- reviewer agents required

The implementation chunk is not done until:

- local tests for that chunk pass
- stale wording scan passes when docs changed
- markdown links pass when docs changed
- at least senior engineering, QA, and security/auth verification are complete or explicitly cancelled and retried
- unresolved verifier concerns are either fixed or recorded for the operator review
- the operator gives final review

Every backend chunk must be judged against Workstream workflow correctness, not generic CRUD completion.

Required test gates across the Week 1 chunks:

- migration tests prove Alembic can create the schema from an empty database and run at least one upgrade/downgrade path during early chunks
- model invariant tests prove project, guide, task, submission, payment, and audit ownership rules
- API smoke tests prove health, project, guide, task, claim, and submission paths
- transition guard tests prove allowed lifecycle moves and block invalid shortcuts
- submission immutability tests prove locked packets cannot be edited in place and replacements create new versions
- auth dependency tests prove missing/invalid tokens fail and valid Flow actor context reaches protected services
- storage abstraction tests prove services use the storage interface and hash validation catches mismatches
- repository hygiene checks prove markdown links and stale wording scans pass when docs change

## Chunk 0: Roadmap And Specification Lock

Scope:

- update the Week 1 roadmap to backend-first
- define modular monolith boundaries
- define per-chunk specification and conditions of satisfaction
- confirm external Flow auth boundary
- keep this as planning only; no backend code

Non-scope:

- FastAPI scaffold
- database migrations
- frontend
- checker implementation
- external source adapters
- marketplace, blockchain, or agent workspace

Conditions of satisfaction:

- roadmap no longer implies frontend is part of the first backend foundation chunk
- roadmap names the backend stack and modular monolith boundaries
- roadmap says Workstream verifies Flow auth tokens instead of managing auth directly
- roadmap defines the review protocol for each implementation chunk
- roadmap defines the required test gates for backend implementation chunks
- stale wording and Markdown link checks pass

Verifier agents:

- senior engineering
- security/auth
- QA/test

## Chunk 1: Backend Scaffold

Scope:

- create the FastAPI backend application structure
- add settings/config
- add health endpoint
- add async database session setup
- add SQLAlchemy base conventions
- add Alembic initialization
- add test setup

Non-scope:

- project/task/submission business logic
- checker runner
- frontend
- external Flow auth network integration beyond interface shape if needed

Expected modules:

- `backend/app/main.py`
- `backend/app/core/`
- `backend/app/api/`
- `backend/app/db/`
- `backend/tests/`
- Alembic config and migration directory

Conditions of satisfaction:

- app starts locally
- health endpoint returns success
- async database session can connect in a test path
- Alembic can create an initial migration path
- Alembic upgrade/downgrade path is covered once the first migration exists
- router/service/repository boundaries are present in structure, even before all modules are implemented
- tests pass

Verifier agents:

- senior engineering
- QA/test
- security/auth

## Chunk 2: Auth And Actor Boundary

Scope:

- define auth verifier interface
- implement Flow token verifier adapter boundary
- add development verifier for local testing
- create current actor dependency
- map trusted token claims into Workstream actor identity and role context

Non-scope:

- password authentication
- user registration
- password reset
- direct ownership of Flow identity

Conditions of satisfaction:

- protected endpoint can resolve current actor
- invalid or missing token is rejected
- actor id is available for audit writes
- actor identity uses stable Flow subject and issuer, not email
- roles/claims source is documented and tested
- no password table or login route exists
- dev verifier is clearly separated from production Flow token verification
- dev/mock auth cannot run in production and is visible in audit context
- permission checks live in service or policy code, not scattered in routers

Verifier agents:

- security/auth
- senior engineering
- QA/test

## Chunk 3: Project And Guide Foundation

Scope:

- project model
- project guide model
- submission artifact policy model
- generated pre-submit checker policy model
- post-submit checker policy model
- review policy model
- revision policy model
- payment policy model
- guide versioning fields
- active guide lock behavior
- base payout and submission artifact policy fields

Non-scope:

- full guide editor UI
- external source adapters
- checker execution

Conditions of satisfaction:

- project can be created
- guide version can be created as draft
- guide version can be activated only when required submission artifact, checker, review, revision, and payment policy fields exist
- active guide can be retrieved for task creation
- editing a draft guide does not mutate historical task context
- migrations and model tests pass

Verifier agents:

- senior engineering
- QA/test
- security/auth

## Chunk 4: Task Queue And Assignment

Scope:

- task model with locked guide and policy context
- worker profile
- reviewer profile
- assignment model
- status transition rules through `IN_PROGRESS`
- audit events for status changes
- skill tags

Non-scope:

- submission artifacts
- checker runs
- human review workflow
- payment execution

Conditions of satisfaction:

- task can be created in `DRAFT`
- task cannot move to `SCREENING` without required fields
- task cannot move to `READY` without locked guide/policy context
- task can move `READY -> CLAIMED -> IN_PROGRESS`
- two workers cannot own the same task unless policy explicitly allows it
- every status change writes an audit event
- audit events include actor id, external subject, issuer, role/claim context, and auth source where relevant
- transition guard tests pass

Verifier agents:

- senior engineering
- QA/test
- security/auth

## Chunk 5: Submission Packet Foundation

Scope:

- submission model
- evidence item model
- artifact/package metadata
- artifact hash manifest
- worker attestation
- submission versioning
- task transition to `SUBMITTED`

Non-scope:

- checker execution
- review decisions
- payment/reputation creation

Conditions of satisfaction:

- worker submits v1 packet against `task_id`
- worker does not provide guide or policy versions
- worker-provided guide or policy version fields are rejected or ignored and cannot mutate task context
- Workstream stamps locked guide and policy versions from task context
- task moves to `SUBMITTED`
- submitted packet can be locked before checker execution
- replacing an artifact creates a new submission version instead of mutating v1
- submission and immutability tests pass

Verifier agents:

- senior engineering
- QA/test
- security/auth

## Week 1 Acceptance Bar

By the end of the week:

- backend scaffold exists and runs
- external Flow auth boundary is designed and enforced at dependency level
- project/guide/task/assignment/submission records exist
- core lifecycle works through `SUBMITTED`
- every status transition is audit-recorded
- submitter packet is simple and task-owned policy context is server-stamped
- tests cover model invariants and transition guards
- no frontend work is required for this acceptance bar
