# Chunk 2 Auth And Actor Boundary Spec

## Scope

Build the Workstream v0.1 authentication boundary.

This chunk defines how FastAPI routes resolve the current actor from an external Flow-issued token without Workstream owning login, signup, password reset, password storage, or primary auth sessions.

## Non-Scope

- password authentication
- user registration
- password reset
- local session ownership
- production Flow network verification
- actor persistence tables
- project/task/submission business logic
- frontend work

## Expected Files And Modules

- `backend/app/interfaces/auth.py`
- `backend/app/adapters/auth/`
- `backend/app/api/deps/auth.py`
- `backend/app/api/routes/auth.py`
- `backend/app/core/permissions.py`
- `backend/app/schemas/auth.py`
- `backend/tests/test_auth.py`

## Architecture Requirements

- Auth verifier behavior is defined by an interface.
- Production Flow verification is represented by an adapter boundary.
- Local development auth is a separate adapter.
- The current actor is resolved by one FastAPI dependency.
- Routers do not own permission logic.
- Permission checks live in service/policy code.
- Actor identity uses stable Flow `subject + issuer`, not email.
- Actor context includes role/claim context for later audit writes.
- Dev/mock auth cannot run in production.
- Dev/mock auth is explicit opt-in only for local, dev, development, or test environments.
- Dev/mock auth has no built-in token default.
- Runtime database configuration comes from environment and does not expose embedded credentials in source defaults.
- Dev/mock auth is visible through actor context and audit context fields.

## Data Model Impact

No database tables are introduced in this chunk.

The in-request actor context must expose:

- `actor_id`
- `external_subject`
- `external_issuer`
- `roles`
- `claim_snapshot`
- `auth_source`
- `is_dev_auth`

## API Impact

Adds:

- `GET /api/v1/auth/me`

This is a protected smoke endpoint used to prove actor resolution. It does not replace Flow login and does not create a session.

## Lifecycle Impact

No Workstream task lifecycle transitions are implemented.

The actor context created here becomes the input later services use for audit attribution and permission checks.

## Security/Auth Impact

- Missing token returns unauthorized.
- Invalid token returns unauthorized.
- Valid dev token resolves an actor only outside production.
- Flow verifier adapter boundary exists but does not fake production verification.
- Workstream does not add local login, signup, registration, password reset, password storage, or session routes.

## Tests Required

- missing bearer token is rejected
- invalid bearer token is rejected
- valid dev token resolves actor id, external subject, external issuer, roles, auth source, and audit context
- actor id is derived from `external_subject + external_issuer`, not email
- dev verifier cannot be created in production
- Flow verifier adapter boundary rejects unsupported local verification
- permission policy allows required roles
- permission policy rejects missing roles
- no local auth/password/session routes exist

## Conditions Of Satisfaction

- protected endpoint resolves current actor
- invalid or missing token is rejected
- actor id is available for audit writes
- actor identity uses stable Flow subject and issuer, not email
- role/claim source is documented in code and tested
- no password table or login route exists
- dev verifier is separate from production Flow verifier
- dev/mock auth cannot run in production and is visible in audit context
- permission checks live outside routers
- backend tests pass
- stale wording scan passes
- Markdown link check passes
- senior engineering verifier passes
- QA/test verifier passes
- security/auth verifier passes

## Reviewer Agents Required

- security/auth
- senior engineering
- QA/test
