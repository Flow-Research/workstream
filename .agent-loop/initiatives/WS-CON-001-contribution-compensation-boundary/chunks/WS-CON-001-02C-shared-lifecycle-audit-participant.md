# Chunk Contract: WS-CON-001-02C - Shared Lifecycle Audit Participant

## Goal and risk

Extend the existing shared AuditEvent repository/service with one typed
caller-transaction lifecycle participant required by REV and CON. L1 audit/
cross-domain-transaction risk.

## Allowed files

```text
backend/app/modules/audit/{schemas,repository,service}.py
backend/tests/test_audit.py
docs/architecture_data_model.md only exact shared-audit ownership note
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-02C.json
```

## Not allowed

```text
AuditEvent schema/migration rewrite
review, contribution, compensation, task, AUTH or outbox event semantics
commit ownership, route, background executor, dependency or CI weakening
```

## Acceptance criteria

- [ ] Typed `LifecycleAuditParticipant` accepts caller AsyncSession and bounded
  canonical event input, reuses AuditRepository, flushes, and never commits.
- [ ] It preserves append-only AuditEvent identity and rejects credentials,
  tokens, provider refs, unbounded payloads and caller-supplied authority facts.
- [ ] Caller rollback removes audit with all other transaction effects; exact
  replay/idempotency ownership is explicit and no second audit ledger appears.
- [ ] REV-04 and CON-07 may depend on the merged interface without importing
  feature services; this chunk implements no feature-specific event.

## Verification and reviewers

Execute the exact clean isolated CON-02C row in `../RUNTIME_VERIFICATION.md`,
then run:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_audit.py -k 'participant and (rollback or payload or boundary or idempotency or replay)')
(cd backend && .venv/bin/python -m coverage report --include='app/modules/audit/*' --fail-under=90)
(cd backend && .venv/bin/ruff check app/modules/audit tests/test_audit.py)
```

Pass requires a non-empty selected test set, flush-only rollback, closed typed
payload enforcement, exact replay idempotency, changed-payload conflict,
repository coverage at least 78 percent in the same clean run, and focused
audit coverage at least 90 percent. Senior engineering, QA/test, security/auth,
product/ops, architecture, docs, reuse/dedup and test-delta are required. Stop
after the feature-neutral participant.
