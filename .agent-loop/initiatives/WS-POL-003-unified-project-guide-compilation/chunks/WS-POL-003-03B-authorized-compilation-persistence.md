# Chunk Contract: WS-POL-003-03B - Authorized Compilation Persistence

Status: Proposed after 03A and AUTH-12I; inactive. Risk: L1.

## Goal

Consume the exact compilation request/execute authorization adapters so PM
dispatch custody and fixed-service immutable compilation persistence are usable.

## Allowed files

Compilation request/service/repository/router/worker composition, AUTH resource
adapter consumption, focused tests, specifications, and WS-POL-003 docs.

## Not allowed

Policy projection writes, approval, live unified worker cutover, checker
execution, broad authority, handles in Celery, or transactions across I/O.

## Acceptance

- PM request records only authorized dispatch/recovery custody and identifiers.
- Worker independently authenticates the fixed service and performs exact
  pre-I/O admission, committed attempt reservation, same-key provider recovery,
  and fresh final result-bound PREP before immutable persistence.
- Compilation/result/evidence commit atomically in the final transaction;
  already-issued provider I/O is represented by durable recovery state.
- Replay/copy/stale/session/transaction/service/resource mismatches fail closed.

## Verification and review

PREP all-pairs, provider uncertainty/recovery, crash, replay, rollback, and 90%
changed-subsystem coverage; all L1 tracks. Human focus: authorization around,
never across, external I/O.
