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
`8d5eb15b`, AUTH-09E merged through PR #157 as `42a89b2d`, and the
availability-neutral ART custody transfer merged through PR #158 as
`be2a79a2`, and the unrelated availability-neutral REV custody transfer merged
through PR #160 as `fe0e4492`. Backend CI sharding and timeout repair merged
through PRs #163 and #164 as `b0f9ad64` and `61bc0390`; signed-start loop-memory
planning merged through PR #165 as `58d0514a`; and AUTH-PREP merged through PR
#162 as `c559d556`. All are integrated into the ART candidate. AUTH-PREP adds no
ART consumer or activation. The three ART internal feature actions remain
assigned to future
`WS-AUTH-001-ART-02D-INTERNAL` activation custody, but remain planned and
inactive.

Verification/put-resolution custody (`02C2`) and the recovery-attempt chain
(`02C3`) are now merged on trusted main; `02C3` merged through PR #174 at
`92b8a7aa`. Signed automation then started `WS-ART-001-02D` on that exact main.

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

`WS-ART-001-02D` is active after the user's signed explicit start on
2026-07-22. It adds hidden, provider-neutral Operator reads, exact retry and
recovery HTTP composition, redacted audit/admission views, bounded admission
pressure metrics, and static inactive readiness. Production composition is
deny-only: all eight Operator actions and three internal actions remain planned
and AUTH retains sole activation custody. AWS live proof, product cutovers,
deletion, retention, and release remain out of scope.

## Next Proposed Chunk

`03` may store and bind guide-source bytes only after 02D merges and receives a
separate explicit start. No deferred provider has a v0.1 chunk.

## Gate

The 02D candidate integrates trusted main `92b8a7aa` without activating ART.
The current gate is deterministic evidence and required internal review,
followed by external CI/review and explicit human merge approval. Production
activation and AWS live proof remain in later owning chunks. No later artifact
chunk starts automatically, and only the user may approve merge.
