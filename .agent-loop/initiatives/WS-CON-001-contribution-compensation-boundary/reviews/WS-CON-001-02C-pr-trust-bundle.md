# PR Trust Bundle: WS-CON-001-02C

## Intent and design

Add the shared flush-only lifecycle-audit participant required by future REV
and CON caller transactions. `LifecycleAuditEventInput` admits only closed
canonical event, entity, reason, and exact event-specific UUID-reference
shapes. `LifecycleAuditParticipant` builds
the historical `legacy_lifecycle` row using fixed internal provenance and asks
`AuditRepository` to return an exact replay or flush the new row without
committing.

Changed reuse of an event ID raises `LifecycleAuditConflict` without echoing
payload data. The generic repository rejects the participant's reserved
`local_lifecycle` writer marker, so callers cannot bypass typed validation.

## Scope

- `backend/app/modules/audit/{schemas,repository,service}.py`
- `backend/tests/test_audit.py`
- exact shared-audit ownership documentation and WS-CON-001 loop evidence

No migration, model, route, worker, feature service, AUTH, REV, contribution,
compensation, task, outbox, dependency, or CI changes.

## Verification

- 39 isolated PostgreSQL audit tests passed.
- 26 focused lifecycle tests passed.
- 11 schema-only lifecycle input tests passed.
- Audit subsystem coverage is 95%.
- Ruff, diff integrity, Markdown links, and stale wording passed.

## Risks and human review focus

- Confirm use of fixed internal values in historical `external_subject` and
  `external_issuer` columns is an acceptable compatibility representation.
- Confirm the closed entity/reference list is sufficient for REV-04B and
  CON-07 without introducing feature-service coupling.
- Confirm exact replay comparison includes every caller-controlled immutable
  field and deliberately excludes only database-generated `created_at`.
- Confirm caller transaction ownership is preserved: the participant flushes
  and never commits or opens another session.

## Review state

Preimplementation architecture conditions and all valid postimplementation
findings are implemented. Senior engineering, QA, security, product/ops,
architecture, docs, reuse/dedup, and test-delta passed. The PR is ready for
external checks and human review.
