# Chunk Contract: WS-REV-001-06 - Claims, Preference, And Timers

## Status

Non-executable split record.

## Children

- `WS-REV-001-06A`: atomic claim and ReviewLease, claim-time materialization
  through 03B's canonical ReviewPacketManifest/item persistence contract, and
  mandatory `WS-CON-001-06` reviewer policy freeze. It owns no packet-manifest
  model, schema, migration, repository, or duplicate persistence abstraction.
- `WS-REV-001-06B`: reviewer-owned release/decline and preference transitions.
- `WS-REV-001-06C`: separate fixed-service preference and lease expiry plus
  request-path lazy recovery.

Each command publishes its own AUTH-first lock order, database-time boundary,
idempotency, concealment, independent-session races, and rollback proof. No
child combines service identities or borrows human/Operator authority.

## Stop condition

Use `CHUNK_MAP.md`; do not execute this parent.
