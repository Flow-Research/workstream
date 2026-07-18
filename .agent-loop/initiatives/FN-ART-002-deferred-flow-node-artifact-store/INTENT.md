# Intent: FN-ART-002 Deferred Flow Node Artifact Store

## Problem

Flow Node may later provide a Flow-owned immutable byte service, but v0.1 must
not operate or depend on it. Any future adoption must replace the configured
object-store adapter without changing Workstream product services or records.

## Success State

```text
focused private Flow Node byte service
-> ArtifactStore v2 conformance
-> FlowNodeArtifactStore
-> explicit maintenance cutover
-> no dual provider fallback
```

## Non-Goals

- no v0.1 dependency or implementation;
- no semantic search, public publishing, peer discovery, or product authority;
- no Workstream review/payment/reputation behavior;
- no migration from S3-compatible storage without explicit later approval.

## Human Gate

This initiative is deferred. Every chunk requires a new explicit plan approval,
start, and merge decision after WS-ART-001-07 proves v0.1.
