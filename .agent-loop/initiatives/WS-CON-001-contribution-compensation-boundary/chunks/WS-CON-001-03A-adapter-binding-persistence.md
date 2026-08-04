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
backend/tests/{test_compensation,test_alembic}.py
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

- [ ] Binding stores project, instrument, typed capability, canonical service
  actor ID, non-secret route identity, state/version, and immutable lifecycle
  timestamps; credentials/provider refs are impossible.
- [ ] Composite constraints preserve project/instrument ownership and valid
  active/suspended/retired transitions.
- [ ] Schema supports callback guards but creates no ActorProfile, identity
  link, ServiceIdentity, static row, adapter, route, or delivery behavior.
- [ ] Upgrade/downgrade and duplicate/state races use isolated PostgreSQL.
- [ ] The migration is allocated from the then-current single head; no fixed
  revision number is reserved until current main is refreshed at chunk start;
  ART #249 has consumed migration `0050`.

## Verification and reviewers

Execute CON-03A in `../RUNTIME_VERIFICATION.md`; changed compensation code is
at least 90 percent. Required tracks: senior, QA, security, product,
architecture, docs, reuse, and test-delta. Stop after schema.
