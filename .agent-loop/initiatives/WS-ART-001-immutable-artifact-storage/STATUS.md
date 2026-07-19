# Status: WS-ART-001 S3-Compatible Object Storage Amendment

## Current State

Original planning merged through PR #97, artifact/LocalStorage foundation
merged through PR #101, the AWS-first object-storage amendment merged through
PR #120 as `4408256`, the external-service adapter foundation merged through
PR #127 as `f64a8e5`, committed-source preparation merged through PR #129 as
`9a04434`, and the ArtifactStore v2 Local clean cut merged through PR #141 as
`a10d901` on 2026-07-18. The user explicitly started `WS-ART-001-02B1` on
2026-07-18.

The planning-only cross-initiative boundary reconciliation merged through
PR #139 as `5d353b6`, and AUTH's owner reconciliation merged through PR #140 as
`d541521`. ART now consumes AUTH's canonical activation-custody and prepared
mutation contracts without editing or activating AUTH runtime behavior.
AUTH-09D-A merged through PR #148 as `99ae4c9` and is integrated into the ART
candidate; AUTH-09D-B remains inactive.

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

`WS-ART-001-02B1` is active. It adds one `S3CompatibleArtifactStore`, runs the
shared ArtifactStore v2 vectors against real digest-pinned MinIO, and validates
an isolated native-AWS workload-identity profile. MinIO is runtime-eligible
only in local/development/test after the PostgreSQL namespace claim. Native AWS
remains runtime-ineligible and fails with
`artifact_provider_live_proof_required` before factory construction,
credential resolution, namespace claim, or provider I/O. No product ingest,
durable admission, put-attempt resolution, verification job, recovery route,
or optional-provider runtime is activated. R2 and Flow Node remain deferred.

## Next Proposed Chunk

`02C1` owns generic durable-byte admission and put-attempt state only after
`02B1` merges and receives a separate explicit start. Neither R2 nor Flow Node
has a v0.1 chunk.

## Gate

The reviewed implementation recorded: "The current gate is deterministic 02B1
proof followed by all nine exact-SHA internal reviewer tracks." After integrating
latest `main`, including merged REV planning, that gate passed again at
`9cd5620e` after addressing all four valid CodeRabbit findings, with no ART
runtime or ownership drift. The remaining gate is the post-fix GitHub Actions
and CodeRabbit rerun plus explicit human review. Durable admission, put attempts,
verification publication, and recovery remain in later owning chunks. No later
artifact chunk starts automatically, and only the user may approve merge.
