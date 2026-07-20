# Status: WS-ART-001 Immutable Artifact Storage

## Current State

Original planning merged through PR #97, artifact/LocalStorage foundation
merged through PR #101, the AWS-first object-storage amendment merged through
PR #120 as `4408256`, the external-service adapter foundation merged through
PR #127 as `f64a8e5`, committed-source preparation merged through PR #129 as
`9a04434`, the ArtifactStore v2 Local clean cut merged through PR #141 as
`a10d901`, and S3-compatible MinIO/AWS preparation merged through PR #151 as
`1b5422fc` on 2026-07-19. ART admission and the put-attempt foundation then
merged through PR #154 as `44f2467c`, and the user explicitly started
`WS-ART-001-02C2` on 2026-07-19.

The planning-only cross-initiative boundary reconciliation merged through
PR #139 as `5d353b6`, and AUTH's owner reconciliation merged through PR #140 as
`d541521`. ART now consumes AUTH's canonical activation-custody and prepared
mutation contracts without editing or activating AUTH runtime behavior.
AUTH-09D-A merged through PR #148 as `99ae4c9`, AUTH-09D-B merged through PR
#152 as `93dd392`, the contributor foundation merged through PR #153 as
`8d5eb15b`, and AUTH-09E merged through PR #157 as `42a89b2d`; all are
integrated into the ART candidate. The three ART internal feature actions
remain planned and inactive.

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

`WS-ART-001-02C2` is active after the user's explicit start on 2026-07-19. It
adds caller-only committed put execution, read-only ambiguous-put resolution,
durable verification jobs and typed receipts, PostgreSQL executor/generation
fencing, bounded publication scanning, and complete-read deadlines. Production
composition remains deny-only: the three internal artifact actions stay
planned, no 02C2 Beat schedule is active, and AUTH retains sole activation
custody. Recovery attempts, Operator routes, product cutovers, deletion, and
background write replay remain out of scope.

## Next Proposed Chunk

`02C3` may add the recovery-attempt and idempotency chain only after 02C2 merges
and receives a separate explicit start. No deferred provider has a v0.1 chunk.

## Gate

Deterministic 02C2 proof and all nine exact-SHA internal reviewer tracks are
complete for reviewed implementation SHA `e59a6dfc`. The current gate is
external CI/review followed by explicit human merge approval. Production
activation and recovery remain in later owning chunks. No later artifact chunk
starts automatically, and only the user may approve merge.
