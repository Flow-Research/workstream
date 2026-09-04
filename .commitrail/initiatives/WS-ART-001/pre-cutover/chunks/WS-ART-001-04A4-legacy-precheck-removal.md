# Chunk Contract: WS-ART-001-04A4 - Legacy Standalone Precheck Removal

Initiative: `WS-ART-001` | Risk: L1 | Status: Superseded by PLAN5

Artifact contract phase: `upload_admission`

## Goal

Historical contract only. PLAN5 proved that removing the shared precheck service
before admission-backed Submission creation exists would create an unchecked
legacy Submission path or force a forbidden compatibility seam. No runtime work
is authorized by this contract. Complete removal is reassigned to 05B.

## Allowed Files

- none; this contract is retained only as durable planning history.

## Not Allowed

- any runtime implementation under the 04A4 identifier;
- partial route-only or service-only removal;
- a private compatibility replacement for the shared legacy guard.

## Acceptance Criteria

- canonical PLAN, CHUNK_MAP, DECISIONS, RISKS, STATUS, and 05B contract assign
  the complete clean cut to 05B;
- 04B1 follows PLAN5 without an intervening partial-removal implementation.

## Verification

Documentation gates only; no application tests are authorized by this
superseded contract.

## Required Reviewers

Architecture, security/auth, product/ops, senior engineering, QA/test, docs,
reuse/dedup, CI integrity, and test delta review PLAN5.

## Human Review Focus

- Does the resequencing prevent both unchecked legacy Submission creation and a
  long-lived compatibility seam?
