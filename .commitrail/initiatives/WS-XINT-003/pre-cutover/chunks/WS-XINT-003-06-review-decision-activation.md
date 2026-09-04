# Chunk Contract: WS-XINT-003-06 — Atomic Review Decision Activation

## Status and risk

Non-implementable planning skeleton after 04. Refresh exact files and commands
on current main before an explicit user request. Requires merged REV-10 first
canonical decision commit plus CON-03C/07, audit, and outbox proof. REV-08 pure
validation is insufficient. L1
canonical judgment, contribution, and conditional-compensation integrity.

## Goal

Activate `review.decision` for exactly `accept`, `needs_revision`, or `reject`.

## Allowed files

Enumerate exact AUTH evaluator/availability parity and integrated tests, docs,
and evidence at start. REV and CON implementation files are read-only
dependencies. REV retains decision and lifecycle ownership; CON retains its
flush-only contribution/award participant.

## Not allowed

New contexts/protocols/principals, REV/CON lifecycle implementation, new
decision values, adjudication, reputation, generic artifact access, optional
CON participant, route release, or post-commit canonical repair.

## Acceptance criteria

- Final PREP consumption binds reviewer/link/grant, lease/queue, project/task,
  assignment, exact Submission and predecessor Review, frozen policies, packet
  and evidence facts, decision/findings/resolutions, request/idempotency, session,
  and transaction.
- Every decision appends immutable Review/finding/resolution history and exactly
  one reviewer contribution. Accept alone creates FinalAcceptance, accepts the
  Task/completes assignment, and creates submitter contribution. Needs revision
  creates the exact initial human revision preparation. Reject creates neither
  FinalAcceptance nor submitter contribution.
- Review, lifecycle effects, CON rows/awards, audit, and outbox commit once or
  roll back together. The CON participant is flush-only and cannot authorize,
  decide, advance lifecycle state, or commit independently.
- Decision versus expiry/revocation/evidence drift/duplicate request races are
  deterministic and fail closed.
- The chunk adds no ActionId, PermissionId, principal, context class, protocol,
  REV/CON lifecycle behavior, or product route.

## Verification and reviewers

Exhaustive branch/fault-injection/concurrency/idempotency tests, 90-percent
coverage, hosted full suite; architecture, security, product/ops, QA, senior,
CON/payment-focused, reuse, docs, test-delta, CI integrity.

## Stop

Merge and stop before revision resubmission activation.
