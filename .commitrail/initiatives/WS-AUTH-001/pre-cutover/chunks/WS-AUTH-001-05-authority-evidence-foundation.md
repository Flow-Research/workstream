# Chunk Contract: WS-AUTH-001-05 - Authority Evidence And Idempotency Foundation

## Status

Split before runtime implementation after required L1 plan review. No parent
chunk implementation is permitted.

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Establish durable authority evidence before actor or grant mutations use it.

## Split result

The original contract combined two persistent subsystem boundaries and was not
credibly reviewable below the L1 size ceiling. Implementation is owned by:

- `WS-AUTH-001-05A` - Shared Audit Ownership And Append-Only Authority Evidence
- `WS-AUTH-001-05B` - Authority Idempotency And Invalidation Foundation

AUTH-05A must merge and complete post-merge memory before AUTH-05B starts.
AUTH-06 must not start until both children merge and their memory is current.

## Preserved boundaries

- Existing `AuditEvent` evolves in place; no parallel authority-event table.
- `AuditRepository` becomes the only supported insert/read implementation.
- Authorization owns idempotency and invalidation orchestration.
- The injected `AsyncSession` remains the unit-of-work boundary.
- No route, permission, grant, actor migration, or product cutover is activated.
- D13 provider-neutral verifier adoption remains a separate reviewed chunk
  after the shared external-service adapter foundation exists.

## Stop condition

Stop at this split record. Implement only one reviewed child contract at a
time.
