# Chunk Contract: WS-REV-001-03 - Review Queue And Lease Persistence

## Status

Non-executable split record. Do not implement or create a merge intent for this
parent.

## Children

- `WS-REV-001-03A` owns queue/lease base persistence and the exact merged
  `WS-CON-001-03B` ContributionPolicyVersion FK.
- `WS-REV-001-03B` is the sole owner of the normalized immutable
  ReviewPacketManifest/item models, schema, migration, repository contract, and
  persistence tests. It starts only after ART merges an exact packet-membership
  relation contract. JSON or opaque binding-ID sets are prohibited. Later claim
  work consumes this canonical persistence contract and may not redefine it.

Each child requires a current-main contract, architecture data-model update,
real-PostgreSQL migration proof, internal review, explicit start, and its own PR.

## Stop condition

Use `CHUNK_MAP.md`; do not execute this parent.
