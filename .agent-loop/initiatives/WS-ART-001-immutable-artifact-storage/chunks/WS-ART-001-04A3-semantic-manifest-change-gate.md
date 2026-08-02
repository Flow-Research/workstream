# Chunk Contract: WS-ART-001-04A3 — Semantic Manifest And Change Gate

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 04A2

## Goal

Build the canonical archive/tree identities and reject exact or semantic
unchanged work before checker or provider I/O.

## Allowed Files

ART manifest/executable normalization, TASK predecessor read capability,
read-only sealed workspace projection, migration only if immutable manifest
control-plane persistence is required, focused tests/docs/CI.

## Not Allowed Changes

Project checker execution, provider I/O, durable admission, Submission/review,
arbitrary permission preservation, file execution, or AUTH activation.

## Acceptance Criteria

Manifest commits normalized paths/types/file hashes/sizes/executable flag;
packaging metadata is excluded; explicit/synthetic directories are canonical;
same archive or manifest as immediate predecessor rejects under lock; executable
changes count, timestamp/compression-only changes do not; fixed modes match all
later materializers.

## Verification Commands

Focused manifest/predecessor/concurrency/mode tests, Ruff, stale scans, hosted
gates, 90% owned subsystem and 78% repository coverage.

## Required Reviewers

Architecture, security, QA, product/ops, senior, CI, docs, reuse, test delta.

## Human Review Focus And Stop Conditions

Ensure semantic equality ignores packaging only, never actual work.
