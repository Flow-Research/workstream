# Chunk Contract: WS-REV-001-12A - Joint Lifecycle Release Control

## Status

Non-executable split record. This canonical parent ID is retained and may not be
reused for projection work.

## Children

- `WS-REV-001-12A1`: persisted controller/phase history/idempotency and typed
  fence/drain ports.
- `WS-REV-001-12A2`: mandatory REV/task/checker command classification and
  fence composition, including checker needs-revision routing.
- `WS-REV-001-12A3`: exact CON writer/dispatcher/callback/cutoff/drain fences.
- `WS-REV-001-12A4`: authorized Operator transition, bounded drain,
  timeout/forward recovery, and crash resume.

Persisted phase denies execution; it does not unregister FastAPI routes, change
AUTH action availability/static membership, or substitute for operational
scheduler suspension. Checker needs-revision routing is allowed wherever initial/
revision checker completion is allowed through `revision_cutover_fenced`, then
denied from `admission_fenced`; human Review preparation remains an internal
consequence of leased `review.decision` completion.

## Stop condition

Use `CHUNK_MAP.md`; do not execute this parent.
