# Chunk Contract: WS-REV-001-12 - Projection And Observability

## Status

Non-executable split record.

## Children

- `WS-REV-001-12P1`: deterministic shared-outbox projection handler and exact
  merged dispatcher/handler-registry composition.
- `WS-REV-001-12P2`: separately authorized artifact-reference reconciliation
  and projection rebuild jobs after ART owns the exact capability.
- `WS-REV-001-12P3`: bounded notifications/admin reads/metrics and
  `ReviewLifecycleDrainObservationPort`.

No child creates a review-private poller, retry ledger, audit table, outbox, or
provider adapter. Each fixed service has its own AUTH identity/action/static row.

## Stop condition

Use `CHUNK_MAP.md`; do not execute this parent.
