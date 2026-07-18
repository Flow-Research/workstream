# Chunk Contract: WS-CON-001-02B - Shared Outbox Dispatcher And Recovery

## Goal and risk

Implement feature-neutral claim/invoke/finalize, retry, dead-letter, replay,
retention, typed handler registry, claim validation, and drain observation. L1
background-execution/operations/auth risk.

## Allowed files

```text
backend/app/modules/outbox/**
backend/app/composition/outbox.py
backend/app/workers/outbox.py
backend/app/workers/celery_app.py only dispatcher task registration
backend/app/core/config.py only bounded outbox/Celery/Redis settings
backend/tests/test_outbox.py
backend/tests/test_config.py only exact new settings
backend/tests/test_authorization.py only exact boundary proof
docs/spec_shared_outbox.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-02B.json
```

## Not allowed

```text
contribution, compensation, review, artifact, or provider semantics
protected feature-handler authority or provider I/O
AUTH implementation edits; dynamic registry/plugins; second outbox
test/coverage/CI weakening
```

## Approved AUTH prerequisites and handoff inputs

- AUTH must first merge the planned `outbox.dispatch` ActionId/PermissionId,
  AUTH custodian, closed `workstream.outbox.dispatcher` ServiceIdentity and
  singleton static row, controlled ActorProfile/link provisioning, AUTH-09E
  admission, typed context, and PR #140 prepared-mutation protocol.
- The handoff supplies AUTH-owned prepare/consume/evaluate ports and the exact
  session/action/actor-reference/idempotency/request-digest binding. CON does
  not register those identifiers, provision service authority, query grants,
  or implement the AUTH evaluator. Matrix and availability remain code-owned
  AUTH validations. The hidden dispatcher stays disabled until later AUTH
  evaluator integration and activation.

## Acceptance criteria

- [ ] Using the approved AUTH handoff, dispatcher claim composition locks and
  recomposes canonical claim facts between AUTH prepare and AUTH
  consume/evaluate; no claim mutation occurs before the supplied authorization
  succeeds.
- [ ] Dispatcher claims with lease/generation fencing, commits and releases all
  locks before invoking a handler, and alone applies typed outcomes to retry/
  dead-letter/final state.
- [ ] Handler receives immutable event/payload/idempotency/claim generation and
  validates it through OutboxClaimValidationPort. It cannot lock or mutate the
  OutboxEvent.
- [ ] Dispatcher authority permits claim/invoke/finalize only. Tests deny every
  contribution, compensation, ART, REV, callback, provider, reconciliation, or
  projection action; a feature handler cannot borrow outbox.dispatch.
- [ ] Each protected handler must present its independently approved AUTH
  service context/action. Registration rejects handlers lacking that manifest.
- [ ] Stable Celery task IDs, bounded leases, retry/dead-letter/replay,
  deterministic backoff, cancellation, crash recovery, and retention are
  covered with isolated PostgreSQL/Redis proof.
- [ ] Same-session drain observation counts pending/claimed/retryable/in-flight
  work without repository leakage or false zero.
- [ ] Missing provisioned dispatcher rows deny dispatch/readiness but do not
  fail app startup or administrative provisioning.
- [ ] Changed subsystem coverage is at least 90 percent; global floor 78.

## Verification

Execute the exact clean isolated CON-02B row in `../RUNTIME_VERIFICATION.md`,
then run:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_outbox.py tests/test_authorization.py tests/test_config.py -k 'dispatcher and (claim or authorization or deny or lease or generation or retry or dead_letter or replay or recovery or drain)')
(cd backend && .venv/bin/python -m coverage report --include='app/modules/outbox/*' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/workers/outbox.py' --fail-under=90)
(cd backend && .venv/bin/ruff check app/modules/outbox app/workers/outbox.py app/workers/celery_app.py app/core/config.py tests/test_outbox.py tests/test_authorization.py tests/test_config.py)
```

Pass requires a non-empty selected test set, real-kernel denial without the
approved AUTH handoff, claim-generation fencing, crash recovery, bounded
retry/dead-letter/replay, accurate drain counts, no handler authority
inheritance, repository coverage at least 78 percent in the same clean run, and
both focused coverage reports at least 90 percent.

## Review and stop

Required tracks include all baseline, architecture, security, product, docs,
reuse, CI integrity, and test-delta. Stop after hidden dispatcher; do not enable
feature execution.
