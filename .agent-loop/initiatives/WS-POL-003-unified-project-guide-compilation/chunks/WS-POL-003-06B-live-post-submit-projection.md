# Chunk Contract: WS-POL-003-06B - Live Post-Submit Projection

Status: Proposed after 06A and AUTH-12G; inactive. Risk: L1.

## Goal

Expose deterministic fixed-service projection plus separate PM
approval/correction under the exact AUTH adapters, with zero additional model
calls.

## Allowed files

Project post-submit service/repository/router, AUTH adapter consumption,
canonical compiler integration, focused tests, specifications, and POL docs.

## Not allowed

Guide/model invocation, checker execution, ART behavior, caller-selected
checkers, legacy post-submit agent method, or partial activation.

## Acceptance

- Projection, approval, and correction each consume their own exact fresh PREP
  and commit product/replay/evidence atomically.
- Every path binds compilation/result/post component and current upstream
  approval hashes; stale or mixed generation denies.
- Continuation, replay, correction, and recovery prove zero provider/model
  calls and no reachable legacy post-submit inference.

## Verification and review

PostgreSQL atomicity/races, all-pairs authorization, zero-call reachability,
hosted coverage, and all L1 tracks.
