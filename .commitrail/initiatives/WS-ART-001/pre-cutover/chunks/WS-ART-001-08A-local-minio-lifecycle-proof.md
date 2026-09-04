# Chunk Contract: WS-ART-001-08A — Local And MinIO Lifecycle Proof

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 07B

## Goal

Prove the v0.1 artifact custody lifecycle through real APIs and durable workers
against LocalStorage and MinIO without weakening production boundaries.

## Allowed Files

Bounded proof harness/fixtures/report, provider conformance tests, operations
documentation, scoped CI wiring, and evidence artifacts.

## Not Allowed Changes

Product shortcuts, direct database mutation, Terminal Benchmark coupling, AWS
activation, new lifecycle features, generic download, or reduced CI gates.

## Acceptance Criteria

- proof covers guide and submission ingest, verification, binding, authorized
  materialization, stale/replay/denial cases, and immutable identity continuity;
- LocalStorage and MinIO satisfy one provider-neutral contract;
- proof uses public/internal supported interfaces and sanitized bounded fixtures;
- failures are reproducible and evidence contains no secrets.

## Verification Commands

Provider conformance suite, lifecycle drill, report validation, coverage, and
hosted Backend/Agent Gates.

## Required Reviewers

Architecture, security, product/ops, QA, senior engineering, CI integrity,
reuse/dedup, test delta, and docs.

## Human Review Focus And Stop Conditions

Confirm the proof exercises production boundaries. Stop before AWS readiness.
