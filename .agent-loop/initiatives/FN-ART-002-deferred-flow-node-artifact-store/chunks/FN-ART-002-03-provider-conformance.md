# Chunk Contract: FN-ART-002-03 Provider Conformance

Initiative: `FN-ART-002` | Risk: L1 | Status: Deferred

## Goal

Prove the focused service against Workstream's exact ArtifactStore v2 contract
and deployable outage/restart behavior.

## Allowed Files

- versioned Workstream-owned conformance fixture copy with source digest
- Flow Node conformance/integration harness
- focused image, health/readiness, migration, and operations files
- test-only fault fixtures isolated from production routes

## Not Allowed

- generic-port exceptions or provider-specific domain fields;
- Workstream product changes;
- dual runtime, fallback, or fake provider mocks as integration proof;
- test controls reachable from the production binary.

## Acceptance Criteria

- all LocalStorage/MinIO ArtifactStore v2 vectors pass unchanged.
- cancellation, exact replay, missing/corrupt bytes, range handling, outage,
  restart, limits, and redaction are proven through real service calls.
- provider revision and image digest are pinned.
- health/readiness never mutates stored content.
- production image route and linked-capability audit excludes test controls and
  unrelated runtime surfaces.
- failures map to the stable Workstream adapter taxonomy.

## Verification

```bash
cargo test --all-targets
docker compose -f <focused-conformance-compose> up --build --abort-on-container-exit
<production-image route and linked-capability audit>
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

Does conformance prove equivalence without hiding Flow Node special cases?
