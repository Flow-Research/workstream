# Chunk Contract: FN-ART-002-04 Workstream Adapter

Initiative: `FN-ART-002` | Risk: L1 | Status: Deferred

## Goal

Implement `FlowNodeArtifactStore` behind ArtifactStore v2 and ADR 0014's typed
factory without changing product services.

## Allowed Files

- one Workstream concrete adapter
- typed secret-safe provider configuration and factory registration
- ArtifactStore conformance and real Flow Node integration tests
- adapter-specific operations docs and chunk memory

## Not Allowed

- product-service/repository/checker concrete adapter imports;
- ArtifactStore generic-port changes;
- fallback, dual factory, service locator, or runtime plugin discovery;
- byte migration or production activation;
- human token forwarding or provider product authority.

## Acceptance Criteria

- the unchanged ArtifactStore v2 conformance suite passes.
- service credentials are injected, rotated, and redacted.
- exact Workstream authorization precedes every dispatch.
- provider IDs/CID/DAG details remain opaque bounded observations.
- LocalStorage and S3CompatibleArtifactStore behavior is unchanged.
- unknown/invalid Flow Node configuration fails closed.
- changed subsystem coverage is at least 90 percent and repository coverage
  does not decrease.

## Verification

```bash
cd backend && .venv/bin/ruff check app tests
cd backend && .venv/bin/pytest tests/test_artifact_store_conformance.py tests/test_flow_node_artifact_store.py -q
python3 scripts/check_stale_artifact_contracts.py
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

Is this a replaceable adapter with zero product-domain leakage?
