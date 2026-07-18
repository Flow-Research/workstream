# Chunk Contract: WS-CON-001-08A - Outbound Compensation Delivery Handler

## Goal and risk

Handle committed fulfillment-request events, persist durable pre-I/O delivery
state, call the typed external adapter after commit, and return a typed outbox
outcome. L1 economic/external-service/auth risk.

## Prerequisites

- CON-07 and shared outbox merged;
- exact outbound-delivery ServiceIdentity and ActionId/static row approved and
  registered as planned by AUTH, or an explicitly approved closed
  dual-principal design;
- provisioned service ActorProfile/link, AUTH-09E admission, typed context, and
  prepared protocol; the action remains planned while this hidden behavior
  merges;
- ADR 0014 typed adapter/factory composition and lifecycle fence port.

## Allowed files

```text
backend/app/modules/compensation/{schemas,repository,service,ports}.py
backend/app/interfaces/compensation.py
backend/app/adapters/compensation/**
backend/app/modules/outbox/handlers.py only explicit handler registration
backend/app/composition/compensation.py
backend/app/workers/compensation.py
backend/app/workers/celery_app.py only delivery task registration
backend/tests/{test_compensation,test_outbox,test_authorization,test_external_service_adapters}.py
docs/spec_contribution_compensation.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-08A.json
```

## Not allowed

```text
outbox claim/finalization transitions; callback behavior
generic dispatcher identity executing delivery
AUTH implementation; provider SDK/concrete adapter import in domain service
database/fence lock held during external I/O
```

## Acceptance criteria

- [ ] Handler validates committed claim generation but never locks/mutates the
  OutboxEvent. Dispatcher later applies its typed outcome.
- [ ] Delivery authority is independent from `outbox.dispatch`. Dispatcher is
  denied delivery; delivery identity is denied dispatch and every other
  handler/action; humans are denied fixed-service execution.
- [ ] Prepared authorization locks service ActorProfile/link and validates exact
  ServiceIdentity/static row/action as code-owned facts. AUTH prepares its exact
  bound handle; CON locks award/binding/delivery rows and recomposes final
  facts; AUTH consumes/evaluates once before durable delivery mutation.
- [ ] Durable in-flight generation and exact event/payload/binding/idempotency
  identity commit before adapter I/O. The already-claimed command resolves its
  immutable obligation root, ordinal, and lifecycle generation under the shared
  `JointLifecycleMutationFence`. In `delivery_draining`, only a same-generation
  root at or below the persisted cutoff may enter durable `in_flight`; no new
  root, requeue, successor, or repair work is allowed.
- [ ] The pre-I/O transaction commits and releases every database transaction
  and lifecycle fence before the adapter call. Finalization occurs in a new
  fenced transaction for the same root. A lost pre-I/O race returns the same
  event to retryable pending without changing award or delivery truth; only the
  shared dispatcher mutates outbox claim/retry/dead-letter state.
- [ ] Adapter result cannot change award identity/quantity. Retry, ambiguous
  completion, acknowledgement, callback-before-ack, cancellation, and replay
  preserve monotonic delivery/receipt truth.
- [ ] Provider I/O is only through typed capability/factory at composition root.
- [ ] Coverage/concurrency/failure proof meets repository floors.
- [ ] Independent-session tests cover dispatch versus cutoff/disable in both
  orders, same-generation pre-cutoff completion, post-cutoff/cross-generation
  denial before provider I/O, and instrumentation proving no advisory fence or
  database transaction is held during adapter I/O.
- [ ] The real kernel continues to deny the planned action. AUTH activation is
  a later checkpoint after this hidden handler and its evaluator composition
  merge.

## Verification

Execute the exact clean isolated CON-08A row in `../RUNTIME_VERIFICATION.md`,
then run:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_compensation.py tests/test_outbox.py tests/test_authorization.py tests/test_external_service_adapters.py -k '(delivery or adapter or fulfillment) and (fence or cutoff or generation or retry or replay or concurrency or authorization or pre_io or transaction)')
(cd backend && .venv/bin/python -m coverage report --include='app/modules/compensation/*' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/workers/compensation.py' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/interfaces/compensation.py' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/adapters/compensation/*' --fail-under=90)
```

Pass requires a non-empty selected test set, pre-I/O durable fencing, no
transaction or lifecycle fence held during adapter I/O, both cutoff race
orders, same-generation pre-cutoff completion, post-cutoff/cross-generation
denial before provider calls, retry/replay and ambiguous-result safety, typed
adapter-factory use, repository coverage at least 78 percent in the same clean
run, and every focused report at least 90 percent.

## Review and stop

All baseline plus architecture, security, product, docs, reuse, CI integrity,
and test-delta. Stop after hidden handler; do not activate the action or
register public routes.
