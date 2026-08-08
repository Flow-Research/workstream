# Chunk Contract: WS-POL-003-05A - Hidden Pre-Submit Approval

Status: Proposed after 04B; inactive. Risk: L1.

## Goal

Build hidden PM approval and trusted effective/pre-submit projection behavior
over the complete immutable unified result.

## Allowed files

Project approval/policy service/repository/schema, ART catalogue/compiler
integration, deny-by-default AUTH seam, focused tests, and WS-POL-003 docs.

## Not allowed

Action activation, public live approval, model calls, post projection,
checker execution, second compiler/registry, or in-place proposal edits.

## Acceptance

- Approval input binds compilation/result/artifact/pre/post component hashes,
  source/setup generation, and both catalogue snapshots.
- The full proposal is reviewable before approval; required gaps block and
  optional gaps require acknowledgement.
- Mandatory platform entries cannot be selected, repeated, weakened, or
  reordered; stale lineage denies.
- Candidate effective/pre writes remain hidden and denied until AUTH-12F4.

## Verification and review

Compiler parity, full-result-before-approval, gap, stale-hash, and denial tests;
all L1 tracks. Human focus: complete proposal and no inference at approval.
