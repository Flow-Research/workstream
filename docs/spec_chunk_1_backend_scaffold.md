# Chunk 1 Backend Scaffold Spec

## Scope

Build the first backend scaffold for Workstream v0.1.

This chunk creates the FastAPI application shell, async database wiring, Alembic migration path, test setup, and clean modular monolith boundaries. It does not implement project, guide, task, assignment, submission, checker, review, payment, or reputation business logic.

## Non-Scope

- frontend work
- local password, login, signup, password reset, or session ownership
- production Flow token verification
- project/task/submission CRUD
- checker runner
- storage implementation beyond interface placement if needed
- external source adapters
- blockchain, marketplace, or agent workspace

## Expected Files And Modules

- `backend/pyproject.toml`
- `backend/alembic.ini`
- `backend/alembic/`
- `backend/app/main.py`
- `backend/app/api/`
- `backend/app/core/`
- `backend/app/db/`
- `backend/app/modules/`
- `backend/app/interfaces/`
- `backend/app/adapters/`
- `backend/tests/`

## Architecture Requirements

- Routers handle HTTP only.
- Services will own workflow rules in later chunks.
- Repositories will own database access in later chunks.
- Interfaces define external boundaries.
- Adapters implement external boundaries.
- Database access uses SQLAlchemy 2.x async.
- Migrations use Alembic.
- API schemas use Pydantic.
- Runtime database configuration targets Postgres.
- Tests may override database configuration for isolated scaffold checks.

## Data Model Impact

No domain tables are introduced in this chunk.

This chunk may define:

- SQLAlchemy declarative base
- shared metadata naming convention
- async engine/session factory
- empty Alembic baseline revision

## API Impact

Adds:

- `GET /health`
- versioned API router mount, currently empty beyond health routing

No protected routes are added in this chunk.

## Lifecycle Impact

No lifecycle transitions are implemented.

The scaffold must leave a clear place for lifecycle/state guard code in later chunks.

## Security/Auth Impact

No authentication behavior is implemented in this chunk.

The scaffold must not add local login, signup, password reset, password storage, or primary session ownership.

Auth interfaces/adapters can be added in Chunk 2.

## Tests Required

- health endpoint returns success
- application object can be created
- settings load with default values
- async database session can execute a simple query through an override test URL
- Alembic upgrade/downgrade path works against an isolated test database URL
- no local login/password route exists

## Conditions Of Satisfaction

- app imports successfully
- app starts through FastAPI application factory
- health endpoint works
- async database session works in a test path
- Alembic has an initial migration path
- tests pass locally
- stale wording scan passes
- Markdown link check passes
- senior engineering verifier passes
- QA/test verifier passes
- security/auth verifier passes

## Reviewer Agents Required

- senior engineering
- QA/test
- security/auth
