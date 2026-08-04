# Chunk Contract: WS-CON-001-03A - Project Compensation Adapter-Binding Persistence

## Goal and risk

Persist immutable `ProjectCompensationAdapterBinding` identity/lifecycle
without adapter behavior. L1 economic/auth/data risk.

This is the recommended first runtime chunk after PLAN4. It depends on merged
outbox persistence only for repository-wide baseline coherence; it does not
depend on the dispatcher, lifecycle audit participant, or AUTH action
registration.

## Allowed files

```text
backend/app/modules/compensation/{__init__,models,schemas,repository}.py
backend/app/db/models.py
backend/alembic/versions/<next>_project_compensation_adapter_bindings.py
backend/tests/{conftest,test_compensation,test_alembic}.py
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-03A.json
```

## Not allowed

```text
AUTH actor/grant/ServiceIdentity/static-matrix edits
adapter, route, background executor, policy, award, receipt or delivery behavior
credentials, secrets, raw provider refs, dependency or CI weakening
```

## Acceptance criteria

- [ ] Binding stores project, instrument, canonical adapter service actor ID,
  non-secret route identity, status, binding-specific lifecycle version, and
  lifecycle actor/timestamp fields. Credentials and provider references are
  impossible because the Pydantic input is closed and the table has no such
  columns.
- [ ] `route_key` is 1-120 ASCII characters matching
  `^[A-Za-z][A-Za-z0-9._:-]{0,119}$` in Pydantic and PostgreSQL. Whitespace,
  slashes, URL/query syntax, `@`, path traversal, control characters, Unicode,
  empty/oversize values, and extra secret/provider fields are rejected.
- [ ] Creation locks and validates the exact adapter `ActorProfile` and its
  identity link: service kind, active profile, active service-kind link, and a
  non-null closed `ServiceIdentity` equal to a caller-supplied expected identity.
  Human, suspended/deactivated, revoked/missing-link, null/mismatched, and
  unrelated service identities fail closed. CON creates no AUTH row or value.
- [ ] Composite constraints preserve project/instrument ownership and valid
  active/suspended/retired row shapes. `binding_lifecycle_version` is positive
  and starts at 1. Creation is active-only with every suspension/retirement
  field null; all lifecycle actor fields reference `actor_profiles`. Future
  transitions must increment the version exactly once and preserve timestamp
  ordering, but this chunk exposes no transition primitive.
- [ ] Schema supports callback guards but creates no ActorProfile, identity
  link, ServiceIdentity, static row, adapter, route, or delivery behavior.
- [ ] Suspend/resume/retire commands are deferred to their owning behavior
  chunks. In particular, no retirement primitive exists until policy, frozen
  work, and unfulfilled-award dependency blockers can be enforced.
- [ ] Upgrade/downgrade and duplicate/state races use isolated PostgreSQL.
- [ ] The migration is allocated from the then-current single head; no fixed
  revision number is reserved until current main is refreshed at chunk start.
  This start is bound to main `1cd9c519` with single head
  `0051_review_queue_foundation`, so the migration is `0052`; stop and re-review
  if either fact changes before publication.

## Verification and reviewers

Execute CON-03A in `../RUNTIME_VERIFICATION.md`; changed compensation code is
at least 90 percent. Required tracks: senior, QA, security, product,
architecture, docs, reuse, and test-delta. Stop after schema.
