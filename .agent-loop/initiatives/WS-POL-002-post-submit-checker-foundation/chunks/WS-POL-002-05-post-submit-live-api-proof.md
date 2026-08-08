# Planning Skeleton: WS-POL-002-05 - Unified Post-Submit Live Proof

Status: Non-executable planning skeleton after reconciled WS-POL-002-04,
WS-POL-003-07, ART-06A/06B, and XINT-06B. Risk: L1. Before human start it must
be expanded on then-current main with explicit allowed/not-allowed file paths,
runnable verification commands, and named reviewer tracks.

## Goal

Prove the sole automatic post-submit checker path end to end without policy
inference or caller-selected execution.

## Allowed

Focused tests/drills, bounded observability and visibility repairs, docs,
evidence, and planning memory.

## Not allowed

Model/agent calls, policy derivation, checker selection, standalone or
per-checker public triggers, alternate submission finalization, review decision
changes, ART provider behavior, or authorization widening.

## Acceptance

- A verified admission becomes exactly one Submission and automatically enters
  post-submit checks under its locked unified compilation lineage.
- The run binds exact Submission/version, compilation/result/post component,
  catalogue hashes, compiled plan, checker versions, ART materialization, and
  attempt/idempotency identities.
- Platform defaults cannot be weakened; project checks can only add registered
  capabilities from the stored compiled plan.
- Retry resumes the same run/plan and cannot choose a checker or duplicate a
  business effect.
- Failures route deterministically to the existing checker/review/revision
  lifecycle without inventing product decision values.
- Contributor, Project Manager, Operator, Audit, and reviewer views remain
  bounded and authorized.
- Instrumented proof records zero post-submit model/provider calls and rejects
  every legacy derivation or alternate trigger path.
- Focused and full hosted tests, stale scans, links, diff integrity, and all L1
  reviewer tracks pass.

## Human review focus

Confirm one automatic checker port, immutable lineage, default-checker
preservation, zero inference, and no alternate trigger.
