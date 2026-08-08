# Chunk Contract: WS-XINT-002-06B — Post-Submit Checker Activation

Parent initiative: `WS-XINT-002` | Risk: L1 | Status: Proposed after POL-06B/07 and ART-06A/06B

## Goal

Activate the fixed post-submit materializer and checker output write/binding
actions after their complete hidden ART/CHECKER behavior exists.

## Allowed Files

AUTH catalogue/matrix/composition, ART/CHECKER authorization adapters and exact
resource facts, focused tests/docs/CI evidence.

## Not Allowed Changes

Pre-submit or contributor action changes, review actions, generic artifact
reads, Submission consumption, or new ActionIds.

## Acceptance Criteria

- only post-submit materialization and checker output write/binding actions
  change availability;
- fixed identities are distinct and cannot substitute for each other;
- facts bind Submission, binding/content/manifest, CheckerRun, checker role,
  unified compilation/result/post component, both catalogue hashes, compiled
  checker plan, generated commitment, request, session, and transaction;
- no action activates for pre-unified, mixed-generation, missing-plan, stale,
  or non-POL-07 lineage;
- denial/replay/stale/cross-resource cases precede byte exposure or mutation;
- no prepared handle is serialized.

## Verification Commands

Focused AUTH/ART/CHECKER tests, stale auth/artifact scans, coverage, and hosted
Backend/Agent Gates.

## Required Reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
reuse/dedup, test delta, and docs.

## Human Review Focus And Stop Conditions

Confirm service separation, exact unified facts, and the sole POL-07 port. Stop
before reviewer activation.
