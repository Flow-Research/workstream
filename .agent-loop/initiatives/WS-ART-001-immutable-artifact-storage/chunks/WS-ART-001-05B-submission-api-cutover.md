# Chunk Contract: WS-ART-001-05B — Submission API And Dispatch Cutover

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after XINT-05B

## Goal

Make verified admission consumption the only contributor Submission path and
dispatch post-submit work using immutable identifiers rather than package data.

## Allowed Files

Submission schemas/router/service, exact legacy field migration/removal,
post-submit dispatch payloads, API examples, focused tests/docs/CI evidence.

## Not Allowed Changes

ZIP inspection, admission production, checker execution, review/contribution,
generic artifact download, AUTH catalogue/availability, or compatibility paths.

## Acceptance Criteria

- the public request accepts an admission identity, not URI/hash/manifest facts;
- caller-owned package identity fields are unreachable and removed safely;
- response exposes immutable Submission/binding identities without provider URLs;
- Celery payloads contain durable identifiers/version facts only;
- old and new paths cannot coexist or create duplicate business effects.

## Verification Commands

Focused API, schema, migration, dispatch, replay, stale-field, coverage, and
hosted Backend/Agent Gates.

## Required Reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
reuse/dedup, test delta, and docs.

## Human Review Focus And Stop Conditions

Review the clean cut and API compatibility impact. Stop before checker changes.
