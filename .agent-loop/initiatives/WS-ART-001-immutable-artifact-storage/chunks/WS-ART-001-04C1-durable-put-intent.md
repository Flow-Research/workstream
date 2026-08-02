# Chunk Contract: WS-ART-001-04C1 — Submission Durable Put Intent

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after XINT-06A

## Goal

Consume the passing scratch result, reauthorize final facts, reserve capacity,
persist one put attempt, and hand the checked ZIP to ArtifactStore once.

## Allowed Files

Submission producer integration with generic admission/put attempt, typed
TASK/PROJECT/AUTH seams, hidden orchestration, tests/docs/scoped CI.

## Not Allowed Changes

Ready admission publication, Submission creation/binding, public route,
provider redesign, second recovery aggregate, retention/deletion, or availability.

## Acceptance Criteria

Fresh transaction-local authority and locked actor/assignment/task/predecessor/
context commit with capacity and put intent before provider I/O; denial/drift
causes no durable/provider effect; exact replay is single-effect; post-intent
ambiguity uses existing observation/recovery; scratch never crosses process.

## Verification Commands

Focused crossed-revocation/admission/put/replay tests, Ruff, hosted gates, 90%
owned subsystem and 78% repository coverage.

## Required Reviewers

Security/auth, architecture, QA, product/ops, senior, CI, docs, reuse, test delta.

## Human Review Focus And Stop Conditions

Provider I/O must be impossible before the durable authorization transaction.
