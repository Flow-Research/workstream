# Plan: FN-ART-002 Deferred Flow Node Artifact Store

## Sequence

1. Isolate the minimum Flow Node byte-service binary and storage primitives.
2. Add a private authenticated API implementing immutable
   put/observe-put-result/open/head.
3. Run Workstream-owned ArtifactStore v2 conformance vectors against it.
4. Implement `FlowNodeArtifactStore` through ADR 0014's typed factory.
5. Perform an explicit maintenance cutover with byte migration and full
   verification; remove the old configured adapter in the same release.

## Boundary

Flow Node owns private bytes and protocol observations only. Workstream owns
authorization, content identity, bindings, receipts, lifecycle, audit,
verification truth, jobs, and recovery. CID/DAG/block details remain bounded
provider observations and never enter the generic content contract.
The future adapter implements the exact v2 `put`, read-only
`observe_put_result`, `open`, and `head` semantics. Observation resolves the
deterministic object identity and reports bounded state; it never asks Flow Node
to replay, recover, overwrite, or otherwise mutate a provider write.

## Cutover Rule

There is no live fallback, dual write, read-through migration, or service
locator. Migration copies every retained replica/object in the old storage
namespace, including completed content that is not yet product-bound, reads it
back completely, verifies Workstream SHA-256/size, records a new replica, and
only then changes the configured adapter during a maintenance barrier. Zero
retained old-namespace replicas may remain unmigrated before old adapter
construction is removed.

## Verification

The same conformance suite that proves LocalStorage/MinIO must pass without
provider-specific exceptions. Private authentication, cancellation, bounded
streams, replay, missing/corrupt bytes, outage, restart, and migration rollback
require real integration proof.

Commands containing angle-bracket placeholders are intentionally unresolved
while the initiative is deferred. Read-only discovery must replace every
placeholder with an exact then-current repository command before any chunk can
move from `Deferred` to `Proposed`.
