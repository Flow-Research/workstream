# Chunk Contract: WS-CON-001-10C - Reconciliation And Projection Executors

## Goal and risk

Execute committed bounded compensation-reconciliation and contribution-
projection-rebuild requests under independent exact fixed-service authority.
L1 background-execution/auth/economic-data risk.

## Prerequisites

- 10B durable request and drain contracts merged;
- exact ServiceIdentity/ActionId/static-row design approved for compensation
  reconciliation and contribution projection rebuild, or explicitly approved
  closed dual-principal evaluators;
- controlled service ActorProfile/link provisioning, AUTH-09E admission,
  typed context, and prepared protocol; both actions remain planned while this
  hidden behavior merges;
- shared outbox claim validation and handler registry.

## Allowed files

```text
backend/app/modules/contributions/{repository,service}.py
backend/app/modules/compensation/{repository,service}.py
backend/app/modules/outbox/handlers.py only explicit registration
backend/app/workers/{contributions,compensation}.py
backend/app/composition/{contributions,compensation}.py
backend/tests/{test_contributions,test_compensation,test_outbox,test_authorization}.py
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-10C.json
```

## Not allowed

```text
generic dispatcher identity executing feature work
human request authority reused without approved dual-principal evaluator
canonical contribution/award/receipt mutation; provider settlement
outbox claim/finalization transitions; AUTH implementation
```

## Acceptance criteria

- [ ] Dispatcher can invoke but is denied both executor actions. Each executor
  is denied dispatch, the other executor's action, delivery/callback/ART/REV
  actions, and every human action outside its exact row.
- [ ] Handler validates committed claim generation; AUTH locks fixed-service
  authority and prepares its exact bound handle; CON locks bounded request/
  product rows and recomposes final facts; AUTH consumes/evaluates once; CON
  then stages result/audit/projection state and returns a typed outcome.
- [ ] Compensation reconciliation compares immutable award/delivery/receipt
  truth and creates durable findings/actions allowed by the approved contract;
  it never changes award amount/eligibility or fabricates receipt truth.
- [ ] Any reconciliation path that creates, requeues, succeeds, or repairs a
  fulfillment obligation is classified as an obligation writer, acquires the
  shared lifecycle fence before allocating/locking its immutable root ordinal,
  and is denied from `commands_draining` onward. Completion-only observation or
  same-root finalization cannot be used to smuggle new work into the drain.
- [ ] Contribution rebuild changes rebuildable projections only and never
  mutates ContributionRecord or CompensationAward.
- [ ] Retry/replay/idempotency and crash fencing preserve request identity.
  Missing service provisioning denies runtime/readiness without failing startup.
- [ ] Coverage, concurrency, and cross-service negative proof meet floors.
- [ ] The real kernel continues to deny both planned executor actions. AUTH
  activation is a later checkpoint after hidden behavior and exact evaluator
  composition merge.

## Verification

Execute the exact clean isolated CON-10C row in `../RUNTIME_VERIFICATION.md`,
then run:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_contributions.py tests/test_compensation.py tests/test_outbox.py tests/test_authorization.py -k '(executor or reconcile or rebuild) and (fence or ordinal or retry or replay or crash or concurrency or unauthorized or deny)')
(cd backend && .venv/bin/python -m coverage report --include='app/modules/contributions/*' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/modules/compensation/*' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/workers/contributions.py' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/workers/compensation.py' --fail-under=90)
(cd backend && .venv/bin/ruff check app/modules/contributions app/modules/compensation app/modules/outbox/handlers.py app/workers/contributions.py app/workers/compensation.py app/composition/contributions.py app/composition/compensation.py tests/test_contributions.py tests/test_compensation.py tests/test_outbox.py tests/test_authorization.py)
```

Pass requires a non-empty selected test set, exact executor isolation,
claim-generation validation, shared-fence-before-ordinal ordering, retry/replay
and crash idempotency, concurrent drain denial of new obligation work,
repository coverage at least 78 percent in the same clean run, and every
focused report at least 90 percent.

## Review and stop

All baseline plus architecture, security, product, docs, reuse, CI integrity,
and test-delta. Stop before AUTH activation and CON-11.
