# Chunk Contract: WS-REV-001-05 - Checker Routing And Queue Views

## Status

Non-executable split record.

## Children

- `WS-REV-001-05A` owns only online checker `allow_review` admission through a
  typed checker-owned caller-transaction participant. Version-1 queue entries
  enter open routing; eligible human-revision entries enter preferred routing.
- `WS-REV-001-05B` owns server-selected current work and bounded admin reads.

Historical admission scan/classification is not a deployment side effect here.
It belongs to 11C under exact `review.reconcile.run` fixed-service authority,
with bounded batches, stable cursor/resume state, database locks, audit/outbox,
counts, duplicate-safe retry, and explicit remediation reporting.

## Stop condition

Use `CHUNK_MAP.md`; do not execute this parent.
