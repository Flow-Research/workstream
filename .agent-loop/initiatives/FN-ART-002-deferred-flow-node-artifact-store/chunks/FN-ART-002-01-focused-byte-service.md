# Chunk Contract: FN-ART-002-01 Focused Byte Service

Initiative: `FN-ART-002` | Risk: L1 | Status: Deferred

## Goal

Isolate the minimum Flow Node runtime required for private immutable byte
put/read/head with bounded streaming and atomic publication.

## Allowed Files

- dedicated Flow Node binary/crate and its exact dependency manifests
- existing storage primitives required by that binary
- provider-owned schema migrations
- focused unit/integration tests, image, and operations docs

## Not Allowed

- Workstream repository changes;
- public publishing, semantic search, peer discovery, or unrelated routes;
- Workstream product state, authorization decisions, or audit;
- authentication API, retain/release, or physical deletion;
- deletion of unrelated Flow Node source before the focused runtime is proven.

## Acceptance Criteria

- only immutable put/read-only-observe-put-result/open/range/head runtime
  capabilities are linked and reachable; observation never replays or mutates a
  write.
- streams, object counts, request sizes, timeouts, and concurrency are bounded.
- immutable publication and exact replay are crash-safe and never overwrite.
- provider-specific CID/DAG facts remain internal observations.
- restart, cancellation, missing/corrupt bytes, and migration tests pass.
- Rust toolchain and dependencies are current, pinned, audited, and container-
  reproducible at implementation time.

## Verification

```bash
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --all-targets
docker build --no-cache -f <focused-image-Dockerfile> .
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

Is this truly a focused byte service rather than the old general runtime?
