# Discovery: FN-ART-002 Deferred Flow Node Artifact Store

The earlier candidate branch
`codex/ws-art-001-fn01-isolation-amendment` at `6cc422d` explored Flow Node
isolation, private service authentication, streaming DAG primitives, and
recovery. It is design input only; its review evidence failed and cannot be
reused as approval.

Before activation, discovery must re-check the then-current Flow Node repository
for byte-ingest, read/range, atomic publication, authentication, persistence,
deployment, migration, and observability boundaries. Workstream's current
ArtifactStore v2 port and conformance suite are authoritative.

Known risks are operating a second service, leaking product semantics into the
provider, provider-specific CIDs entering generic contracts, dual-runtime
fallback, incomplete migration, and service authentication drift.
