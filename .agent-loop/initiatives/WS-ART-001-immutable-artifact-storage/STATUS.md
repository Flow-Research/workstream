# Status: WS-ART-001 S3-Compatible Object Storage Amendment

## Current State

Original planning merged through PR #97, the artifact/LocalStorage foundation
merged through PR #101, and the AWS-first object-storage amendment merged
through PR #120 on 2026-07-15 as `4408256`. No artifact implementation chunk
is active.

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

## Active Work

None. The amendment's reviewed planning SHA was `1545d9a`; its final
evidence-bound branch head was `f57dad8`. The merged plan does not itself
configure AWS S3, operate Flow Node, add a deferred provider, or activate
artifact routes.

## Next Proposed Chunk

`WS-ART-001-02A1` remains inactive until this post-merge memory update merges
and the user starts it explicitly. It installs only the shared typed
external-service adapter/factory foundation. `02A2` adds committed-source
preparation and narrows LocalStorage internals without changing the active
port. `02A3` performs the atomic ArtifactStore v2/LocalStorage/schema cut and
removes `flow_node`. `02B1` then owns MinIO and AWS S3. There is no active R2
chunk.

## Gate

PR #120 is merged. Agent Gates and Backend passed on final branch head
`f57dad8`. CodeRabbit did not perform a fresh final-head review because its
review limit was reached; that fact is recorded separately and no CodeRabbit
findings are claimed.

Deterministic proof passes: Ruff; stale artifact, authorization, and Workstream
wording scans; loop-memory state; 75 changed Markdown links; diff hygiene; the
runtime-scope guard; and 44 agent-gate regression tests in a PEP 668-safe,
hash-pinned temporary environment.

Evidence:

- `reviews/WS-ART-001-OBJECT-STORAGE-AMENDMENT-internal-review-evidence.md`
- `reviews/WS-ART-001-OBJECT-STORAGE-AMENDMENT-pr-trust-bundle.md`
- `reviews/WS-ART-001-OBJECT-STORAGE-AMENDMENT-external-review-response.md`
- `reviews/WS-ART-001-OBJECT-STORAGE-AMENDMENT-post-merge-memory-internal-review-evidence.md`
- `reviews/WS-ART-001-OBJECT-STORAGE-AMENDMENT-post-merge-memory-external-review-response.md`
- `reviews/WS-ART-001-OBJECT-STORAGE-AMENDMENT-post-merge-memory-pr-trust-bundle.md`

The current gate is to merge this post-merge memory update and stop. Do not
start `WS-ART-001-02A1` automatically.
