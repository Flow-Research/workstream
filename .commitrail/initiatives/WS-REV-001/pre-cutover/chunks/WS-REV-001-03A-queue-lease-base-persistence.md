# Chunk Contract: WS-REV-001-03A — Queue And Lease Persistence Split

## Status

Non-executable parent split record. PLAN4 replaces the former combined
queue/lease child with 03A1 and 03A2.

## Children

- `WS-REV-001-03A1` owns queue and admission-idempotency persistence only.
- `WS-REV-001-03A2` owns lease and preference persistence only.

No implementation or PR may use this parent ID.

## Stop condition

Use the two child contracts and stop after each child.
