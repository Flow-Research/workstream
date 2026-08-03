# Chunk Contract: WS-XINT-003-03B — Reviewer Claim Activation

## Status and risk

Non-implementable planning skeleton after 03A. Refresh exact files and commands
on current main before an explicit user request. L1 reviewer mutation authority.

## Goal

Activate only `review.claim` against merged REV-03B/06A, CON-06, and exact ART
packet proof. Release, decline, timers, context, and decision remain unavailable.

## Allowed files

Enumerate exact AUTH evaluator/availability/parity and integrated
claim/lease/packet tests, docs, and evidence at current-main start. REV, CON,
and ART implementation files are read-only dependencies.

## Not allowed

New contexts/protocols/principals, REV/CON/ART lifecycle implementation,
release/decline/timers, decision/revision behavior, or product route release.

## Acceptance criteria

- Exact reviewer grant, self-review denial, global reviewer lease limit, policy
  freeze, and packet-manifest binding are recomposed after final locks.
- Crossed claims produce one winner and no partial lease/packet/policy state.
- Revocation, stale admission, copied/replayed/wrong-session handles, and
  cross-project/task/submission requests deny atomically.
- The chunk adds no ActionId, PermissionId, principal, context class, protocol,
  REV lifecycle behavior, or product route.

## Verification and reviewers

Focused service-command/PostgreSQL race/matrix tests, Ruff, coverage and hosted gates;
architecture, security, product/ops, QA, senior, CI, reuse, docs, test-delta.

## Stop

Merge and stop before release/decline activation.
