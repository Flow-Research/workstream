# Chunk Contract: WS-REV-001-11 - Administrative Recovery And Reconciliation

## Status

Non-executable split record.

## Children

- `WS-REV-001-11A`: privileged queue/lease override, correction, force release,
  and close commands.
- `WS-REV-001-11B`: covered PM context repair and D6 exhaustion close. Repair
  cannot bypass a frozen limit/deadline.
- `WS-REV-001-11C`: reconciliation persistence/generation, authority-
  invalidation and general jobs, plus historical admission scan with exact
  invocation, batching, stable resume cursor, locks, audit/counts, and reports.
- `WS-REV-001-11D`: Operator closure only for truly rootless/ambiguous legacy
  obligations and narrow delegation to ART Operator recovery.

Recoverable checker-rooted history is not legacy-unrecoverable. Every child has
separate action/service identity, command lock order, schema/state docs, races,
and rollback evidence.

## Stop condition

Use `CHUNK_MAP.md`; do not execute this parent.
