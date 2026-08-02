# Chunk Contract: WS-ART-001-04A1 — Legacy Contributor Intake Removal

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 03C

## Goal

Remove legacy multi-step upload-session/item contributor reachability and its
unused schema before building the one-ZIP replacement.

## Allowed Files

ART upload models/migration/repository/routes/schemas, static architecture and
migration tests, stale-contract/docs, and scoped CI evidence.

## Not Allowed Changes

Replacement upload route, ZIP parsing, provider I/O, Submission/checker/review,
AUTH catalogue/availability, compatibility aliases, or fabricated backfill.

## Acceptance Criteria

No route, command, service matrix lookup, model, or schema can create/use the
old intake; historical audit values remain readable where required; populated
unsafe downgrade/upgrade refuses honestly; no new intake becomes reachable.

## Verification Commands

Focused Alembic/architecture/route tests, Ruff, stale scans, hosted Backend and
Agent Gates, repository 78% and changed subsystem 90% coverage.

## Required Reviewers

Architecture, security/auth, QA, product/ops, senior, CI, docs, reuse, test delta.

## Human Review Focus And Stop Conditions

Prove deletion without opening a replacement or losing historical evidence.
