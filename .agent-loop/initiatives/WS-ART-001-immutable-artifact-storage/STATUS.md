# Status: WS-ART-001 S3-Compatible Object Storage Amendment

## Current State

Original planning merged through PR #97, artifact/LocalStorage foundation
merged through PR #101, the AWS-first object-storage amendment merged through
PR #120 as `4408256`, the external-service adapter foundation merged through
PR #127 as `f64a8e5`, and committed-source preparation merged through PR #129
as `9a04434` on 2026-07-16. The user explicitly started
`WS-ART-001-02A3` on 2026-07-16.

The planning-only cross-initiative boundary reconciliation merged through
PR #139 as `5d353b6`, and AUTH's owner reconciliation merged through PR #140 as
`d541521`. ART now consumes AUTH's canonical activation-custody and prepared
mutation contracts without editing or activating AUTH runtime behavior.

The Flow Node-focused amendment candidate `6cc422d` passed deterministic checks
but failed internal review on recovery/API completeness. Before repair, the user
approved a first-principle change on 2026-07-14:

```text
v0.1 production bytes -> S3CompatibleArtifactStore -> AWS S3
local/CI proof bytes   -> S3CompatibleArtifactStore -> MinIO
development bytes     -> LocalStorageAdapter
future optional bytes -> Flow Node adapter initiative
```

The failed Flow Node candidate and every reviewer session are closed. It is not
approval or reusable evidence. Its source remains on branch
`codex/ws-art-001-fn01-isolation-amendment` for the deferred Flow Node plan.

## Current Work

`WS-ART-001-02A3` implementation and merged-main deterministic repair are
complete. PR #141 is open. Exact-SHA review found and repaired a residual
LocalStorage startup race, typed-factory startup mismatch, and vague Operator
resource vocabulary. Fresh deterministic coverage and all required internal
reviewer tracks passed; external checks are now pending. Its approved
boundary atomically replaces ArtifactStore v1 with byte-only v2, migrates
LocalStorage and the empty pre-production artifact schema, installs the
immutable storage-namespace fence,
removes dormant `flow_node` configuration, and activates startup plus periodic
scratch cleanup. It does not activate product ingest, durable admission,
put-attempt resolution, verification jobs, or recovery.

## Next Proposed Chunk

`02B1` owns the S3-compatible adapter, MinIO proof, and AWS S3 profile after
`02A3` merges and receives a separate explicit start. There is no active R2 or
Flow Node chunk.

## Gate

All reviews before the latest repairs are retained as history, not reused as
final provenance. Deterministic proof and exact-SHA internal review have passed.
The current gate is GitHub Actions, CodeRabbit, and explicit human review.
Durable admission, put attempts, verification publication, and recovery remain
in their later owning chunks. No
later artifact chunk starts automatically, and only the user may approve merge.
