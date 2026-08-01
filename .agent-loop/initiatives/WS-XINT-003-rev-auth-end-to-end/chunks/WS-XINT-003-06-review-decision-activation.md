# Chunk Contract: WS-XINT-003-06 — Atomic Review Decision Activation

## Status and risk

Non-implementable planning skeleton after 05. Refresh exact files and commands
on current main before an explicit user request. Requires merged hidden REV
decision plus CON participant. L1
canonical judgment, contribution, and conditional-compensation integrity.

## Goal

Activate `review.decision` for exactly `accept`, `needs_revision`, or `reject`.

## Allowed files

Enumerate exact REV decision composition, AUTH final context/activation parity,
CON typed participant wiring, route, tests, docs, and evidence at start. CON may
only flush the typed facts prepared by REV/AUTH; it performs no authority
evaluation, decision, or lifecycle work. REV retains decision and lifecycle
ownership.

## Not allowed

New decision values, adjudication, reputation, generic artifact access, optional
CON participant, manual FinalAcceptance route, or post-commit canonical repair.

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

## Verification and reviewers

Exhaustive branch/fault-injection/concurrency/idempotency tests, 90-percent
coverage, hosted full suite; architecture, security, product/ops, QA, senior,
CON/payment-focused, reuse, docs, test-delta, CI integrity.

## Stop

Merge and stop before revision resubmission activation.
