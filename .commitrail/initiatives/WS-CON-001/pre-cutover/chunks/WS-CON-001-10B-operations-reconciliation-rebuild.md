# Chunk Contract: WS-CON-001-10B - Operations Requests, Reads, And Drain Observation

## Goal and risk

Implement hidden bounded status/audit reads, binding retirement, durable
reconciliation/rebuild request creation, and fulfillment drain observation.
Execution belongs to 10C. L1 operations/auth/data risk.

## Allowed files

```text
backend/app/modules/contributions/{schemas,repository,service}.py
backend/app/modules/compensation/{schemas,repository,service,ports}.py
backend/app/modules/audit/{schemas,repository,service}.py only bounded WS-CON projection
backend/app/api/internal_operations.py
backend/app/composition/{contributions,compensation}.py
backend/tests/{test_contributions,test_compensation,test_authorization,test_outbox,test_audit}.py
docs/operations_payment_reputation.md only implemented WS-CON operations
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-10B.json
```

## Not allowed

```text
async reconciliation/rebuild execution or provider I/O
outbox dispatcher/transition implementation; immutable truth repair
AUTH implementation; production router registration; CI weakening
```

## Approved AUTH prerequisites and handoff inputs

- D11 must be final and AUTH must first merge the approved binding-retire,
  delivery-reconcile, status, reconcile-request, rebuild-request, and audit
  ActionIds with exact candidates, typed contexts, prepared protocol, and AUTH
  custodians. CON neither registers nor activates them.
- The handoff supplies AUTH-owned prepare/consume/evaluate ports. AUTH prepares
  authority first and consumes/evaluates the recomposed facts; the route owns
  the single commit.

## Acceptance criteria

- [ ] Every mutation uses the supplied PR #140 handoff: CON locks and
  recomposes final product facts between AUTH prepare and AUTH
  consume/evaluate, and stages no request/retirement mutation beforehand.
- [ ] Human operations create bounded durable idempotent requests only; they do
  not execute reconciliation/rebuild under human or dispatcher authority.
- [ ] Binding retirement locks policy/assignment/lease/award/delivery/receipt
  dependencies and denies active/unfinished/unfulfilled references in both race
  orders. Exact prior receipt replay remains the only post-retirement path.
- [ ] Audit read/export enforces purpose/scope/range/redaction with no provider
  or sensitive failure leakage.
- [ ] `FulfillmentLifecycleDrainObservationPort` reports pending/claimed/
  retryable outbox work, durable in-flight delivery, and nonterminal callback
  obligations through typed outbox capability, plus the current maximum
  immutable `fulfillment_obligation_ordinal`; zero is valid only when no root
  exists. It never imports an outbox or lifecycle-control repository.
- [ ] Observation uses the caller AsyncSession, is bounded/read-only, never
  commits or calls a provider, and never returns false zero while remote I/O or
  terminal receipt remains possible. Caller-supplied timestamps, ordinals,
  generation, or event IDs cannot substitute.
- [ ] AUTH later activates after hidden behavior; 10C waits for approved
  executor identities/actions/static rows.

## Verification

Execute the exact clean isolated CON-10B row in `../RUNTIME_VERIFICATION.md`,
then run:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_contributions.py tests/test_compensation.py tests/test_authorization.py tests/test_outbox.py tests/test_audit.py -k '(operation or retirement or reconcile or rebuild or audit or drain) and (race or lock or authorization or idempotency or ordinal or false_zero or provider)')
(cd backend && .venv/bin/python -m coverage report --include='app/modules/contributions/*' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/modules/compensation/*' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/modules/audit/*' --fail-under=90)
(cd backend && .venv/bin/ruff check app/modules/contributions app/modules/compensation app/modules/audit app/api/internal_operations.py app/composition/contributions.py app/composition/compensation.py tests/test_contributions.py tests/test_compensation.py tests/test_authorization.py tests/test_outbox.py tests/test_audit.py)
```

Pass requires a non-empty selected test set, both retirement race orders,
prepared-authorization negatives, idempotent bounded requests, exact drain
counts and maximum ordinal without false zero, zero provider calls, repository
coverage at least 78 percent in the same clean run, and every focused report at
least 90 percent.

## Review and stop

Required tracks: senior, QA, security, product, architecture, docs, reuse, and
test-delta. Stop before executor work.
