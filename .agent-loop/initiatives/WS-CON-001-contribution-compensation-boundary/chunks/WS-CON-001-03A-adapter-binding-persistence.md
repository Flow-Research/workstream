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
backend/app/modules/compensation/{__init__,models,schemas}.py
backend/app/db/models.py
backend/alembic/versions/<next>_project_compensation_adapter_bindings.py
backend/tests/{conftest,test_compensation,test_alembic,test_review_queue_persistence}.py
backend/scripts/run_test_lanes.py
docs/{architecture_data_model,spec_contribution_compensation}.md
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
- [ ] This schema chunk exposes no binding-creation repository or service.
  `adapter_actor_id` is only a canonical ActorProfile FK at this layer. The
  04A behavior chunk must wait for AUTH to approve the exact compensation
  adapter identity/capability contract, then lock and validate its active
  service profile and link. Existing ART/REV identities are not valid positive
  compensation-adapter evidence. CON creates no AUTH row or value.
- [ ] Composite constraints preserve project/instrument ownership. This chunk
  permits only active rows at lifecycle version 1 with every
  suspension/retirement field null; all lifecycle actor fields reference
  `actor_profiles`. Future lifecycle behavior migrations may expand the row
  shapes only when their guards exist. Future
  transitions must increment the version exactly once and preserve timestamp
  ordering. Until the owning behavior chunks install those guards, PostgreSQL
  rejects every update to a created binding.
- [ ] Schema supports callback guards but creates no ActorProfile, identity
  link, ServiceIdentity, static row, adapter, route, or delivery behavior.
- [ ] Suspend/resume/retire commands are deferred to their owning behavior
  chunks. In particular, no retirement primitive exists until policy, frozen
  work, and unfulfilled-award dependency blockers can be enforced.
- [ ] Upgrade/downgrade and duplicate/state races use isolated PostgreSQL.
- [ ] The migration is allocated from the then-current single head; no fixed
  revision number is reserved until current main is refreshed at chunk start.
  This start is reconciled to main `b47a7e64` with single head
  `0052_legacy_intake_removal`, so the migration is `0053`; stop and re-review
  if either fact changes before publication.

## Verification and reviewers

Execute CON-03A in `../RUNTIME_VERIFICATION.md`; changed compensation code is
at least 90 percent. Required tracks: senior, QA, security, product,
architecture, docs, reuse, and test-delta. Stop after schema.
