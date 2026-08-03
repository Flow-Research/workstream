# Chunk Contract: WS-CON-001-03D - Delivery, Receipt, And Status Persistence

## Goal and risk

Persist outbound identity, acknowledgement, immutable fulfillment receipts and
rebuildable status separately. L1 payment/audit risk.

## Allowed files

```text
backend/app/modules/compensation/{models,schemas,repository}.py
backend/app/db/models.py
backend/alembic/versions/<next>_compensation_delivery_receipts.py
backend/tests/{test_compensation,test_alembic}.py
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-03D.json
```

## Not allowed

```text
background executor, callback, adapter, router or reconciliation behavior
provider request/attempt/balance, points ledger or settlement data
raw callback bodies, headers, signatures, URLs/endpoints, auth tokens,
unbounded provider messages/codes, opaque provider references or PII
AUTH/ART edit, dependency or CI weakening
```

## Acceptance criteria

- [ ] Immutable award/event/payload/binding/idempotency identities are retained;
  acknowledgement is not fulfillment; receipts are append-only and terminal.
- [ ] Closed stored values are exact: receipt `reported_status` is `fulfilled`
  or `failed`; delivery status is `pending_delivery` or
  `acknowledged_by_adapter`; fulfillment status is `pending`, `failed`, or
  `fulfilled`. No synonym or provider status is persisted.
- [ ] Delivery state durably represents fenced pre-I/O `in_flight` ownership,
  the originating dispatcher claim generation, retryable recovery and callback
  suppression without storing a provider payment attempt. Crash recovery cannot
  erase or guess whether remote I/O may have started.
- [ ] Every fulfillment-obligation root has one immutable, database-allocated,
  monotonically increasing `fulfillment_obligation_ordinal` and exact lifecycle
  generation lineage. Requeue, successor, and repair rows retain their canonical
  root identity; they do not allocate a second root ordinal. Uniqueness and
  immutability constraints support REV-12A cutoff capture without making the
  ordinal a caller-supplied or provider field.
- [ ] Status is rebuildable and cannot overwrite award/receipt truth.
- [ ] Callback-before-ack, duplicate exact receipt and changed receipt are
  representable without provider-attempt/balance/ledger data.
- [ ] Receipt storage is a closed allowlist: bounded binding-scoped non-secret
  event/reference identifiers, the exact canonical award quantity and binding
  unit, closed statuses/failure codes, platform-generated digests derived only
  from approved stored receipt fields, and timestamps. Digests derived from
  provider bodies, tokens, signatures, URLs, PII, balances, ledgers, settlement
  data, or any other forbidden input are rejected. Raw bodies, headers, signatures,
  URLs/endpoints, tokens, unbounded strings, PII, balances, ledgers, settlement
  data, and opaque provider references are rejected rather than redacted into
  durable truth.
- [ ] State constraints permit failed then fulfilled, prohibit any transition
  away from fulfilled, prohibit partial fulfillment, and preserve every failed
  receipt without allowing it to mutate award quantity or truth.
- [ ] Upgrade/downgrade and receipt/delivery races use isolated PostgreSQL.

## Verification and reviewers

Execute CON-03D in `../RUNTIME_VERIFICATION.md`; include rejection tests for
every forbidden receipt field, every forbidden digest input, quantity/unit
mismatch, and read/export non-disclosure proof. Changed
compensation code is at least 90 percent. Senior engineering, QA/test, security/auth, product/ops,
architecture, docs, reuse/dedup and test-delta are required. Stop after schema.
