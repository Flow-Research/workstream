# Chunk Contract: WS-POL-003-06A - Hidden Post-Submit Projection

Status: Proposed after 05B; inactive. Risk: L1.

## Goal

Build hidden deterministic projection and separate approval/correction behavior
from the post-submit component already stored in the unified result.

## Allowed files

Project post-submit compiler/service/repository/schema, canonical CHECKER/POL
catalogue projection, deny-by-default AUTH seam, focused tests, and POL docs.

## Not allowed

Action activation, live routes, guide rereads, any model call, checker
execution, new registrations, or reuse of agent provenance by manual policy.

## Acceptance

- Projection binds compilation/result/post component, approved upstream chain,
  catalogue snapshot, setup generation, and deterministic output hash.
- Unknown/wrong-stage/default-repeating entries fail closed.
- Correction requires new unified generation or separately proven manual
  provenance; it cannot rederive from the guide.
- Candidate mutations remain denied until AUTH-12G.

## Verification and review

Zero-call, stale/replacement, catalogue/default, correction, denial, and race
tests; all L1 tracks. Human focus: deterministic projection only.
