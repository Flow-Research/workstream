# Status: WS-ART-001 Immutable Artifact Storage

## Current State

Original planning merged through PR #97, artifact/LocalStorage foundation
merged through PR #101, the AWS-first object-storage amendment merged through
PR #120 as `4408256`, the external-service adapter foundation merged through
PR #127 as `f64a8e5`, committed-source preparation merged through PR #129 as
`9a04434`, the ArtifactStore v2 Local clean cut merged through PR #141 as
`a10d901`, and S3-compatible MinIO/AWS preparation merged through PR #151 as
`1b5422fc` on 2026-07-19. The user explicitly started `WS-ART-001-02C1` on
2026-07-19.

The planning-only cross-initiative boundary reconciliation merged through
PR #139 as `5d353b6`, and AUTH's owner reconciliation merged through PR #140 as
`d541521`. ART now consumes AUTH's canonical activation-custody and prepared
mutation contracts without editing or activating AUTH runtime behavior.
AUTH-09D-A merged through PR #148 as `99ae4c9`, AUTH-09D-B merged through PR
#152 as `93dd392`, and the contributor foundation merged through PR #153 as
`8d5eb15b`; all are integrated into the ART candidate. AUTH-09E remains
inactive.

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

`WS-ART-001-02C1` is active. It adds the PostgreSQL durable-byte admission
ledger, closed internal guide/contributor/checker-output requests, and one
`prepared` `ArtifactPutAttempt` created atomically before provider I/O. Scope
limits are explicit configuration; callers cannot supply scope collections;
exact content is charged once per task, producer, project, and deployment
scope. Provider execution, verification, publication, recovery, routes, and
product cutover remain inactive. Native AWS remains runtime-ineligible. R2 and
Flow Node remain deferred.

Final implementation SHA `535069cfb1a7312d731bb14a6023ceb0894402e9`
passed 371 focused tests with 94.02 percent scoped coverage and all nine
required internal reviewer tracks. The current gate is publication of that
reviewed candidate to existing PR #154 followed by fresh GitHub and CodeRabbit
evidence.

## Next Proposed Chunk

`02C2` may add fenced put resolution and verification publication only after
`02C1` merges and receives a separate explicit start. Neither R2 nor Flow Node
has a v0.1 chunk.

## Gate

The current gate is deterministic 02C1 proof followed by all nine exact-SHA
internal reviewer tracks; that gate is complete. GitHub Actions, CodeRabbit,
and explicit human review remain pending on the published final candidate.
Provider execution, verification publication, and recovery remain in later
owning chunks. No later artifact chunk starts automatically, and only the user
may approve merge.
