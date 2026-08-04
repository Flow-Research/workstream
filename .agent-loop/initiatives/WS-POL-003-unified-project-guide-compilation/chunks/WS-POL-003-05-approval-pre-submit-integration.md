# Chunk Contract: WS-POL-003-05 - Approval and Pre-Submit Integration

Status: Proposed after 04. Risk: L1.

## Goal

Bind Project Manager approval to the exact immutable compilation and compile
approved project pre-submit bindings through ART-04B1's effective-plan
compiler while preserving its platform entries as mandatory and non-selectable.

## Allowed files

Project policy approval/service/repository/router/schema surfaces,
ART-04B1 catalogue/compiler integration,
authorization resource composition, focused tests, and specifications.

## Not allowed

Second registry/compiler, platform-default selection, checker execution,
post-submit compilation, task/review/payment behavior, or in-place agent edits.

## Acceptance

- Approval locks exact compilation/result/artifact/pre-submit hashes.
- Platform defaults are composed only by ART and cannot be selected, repeated,
  weakened, reordered, or downgraded.
- Required capability gaps block approval/activation with exact operator code.
- Catalogue/source/generation/projection changes stale prior approval.
- Effective and pre-submit outputs commit atomically with authorization evidence.
- The approved project plan and mandatory ART platform entries compose only
  through the later single checker-service pre-submit command; this chunk does
  not change ART or expose an execution route.

## Verification and review

Postgres approval races, stale hashes, default isolation, compiler parity,
AUTH denial, and task-lock regression tests. Required reviewers: all L1 tracks.
