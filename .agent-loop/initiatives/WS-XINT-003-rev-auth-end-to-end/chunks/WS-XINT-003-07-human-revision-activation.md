# Chunk Contract: WS-XINT-003-07 — Human Revision Submission Authority Activation

## Status and risk

Non-implementable planning skeleton after 06. Refresh exact files and commands
on current main before an explicit user request. L1 replacement Submission
authority and immutable predecessor lineage.

## Goal

Extend the already XINT-002-owned preparation/`submission.create` evaluators
with the closed human-review revision context after REV-09A1 through 09B. This
chunk does not take availability custody from XINT-002. No separate
response/finding artifact upload is approved; XINT-002-07B remains reserved.

## Allowed files

Enumerate exact AUTH evaluator integration and integrated tests/docs/evidence at
start. REV, Task/Submission, and XINT-002 implementation files are read-only
dependencies.

## Not allowed

New contexts/protocols/principals/actions, REV/ART/Task/Submission lifecycle
implementation, checker-remediation conflation, guide/policy rebasing outside approved REV
rules, deadline/round bypass, mutable findings, synthetic Review, or a second
submission authorization protocol.

## Acceptance criteria

- Contributor Task Context read returns only the validated current preparation
  head/digest and frozen or approved rebased context; it never falls back to a
  stale or moving guide context.
- Authority binds the exact Review(needs_revision), unresolved blocking
  findings and reviewer note, active preparation head/digest,
  predecessor Submission, active/replacement assignment, project/task, locked
  or approved rebased guide/policies, deadline, and remaining round.
- Predecessor advancement, preparation replacement, finding changes,
  expiry/limit exhaustion, revocation, cross-project/task/submission, copied or
  replayed handles deny without storage intent or provider I/O.
- Exactly one N+1 Submission consumes one preparation/obligation; concurrent
  attempts have one winner and preserve all prior immutable history.
- Human and checker revision sources remain mutually exclusive.
- XINT-002-07B remains reserved and unavailable. The new contributor ZIP is the
  revision artifact; no parallel response-artifact binding path exists.
- The chunk adds no availability transition, ActionId, PermissionId, principal,
  context class, authorization protocol, lifecycle behavior, or product route.

## Verification and reviewers

Concurrency, predecessor/rebase/deadline/round/replacement-contributor matrices,
ART fault injection, coverage and hosted gates; full L1 reviewer set.

## Stop

Merge the coordination/activation evidence and stop before privileged recovery.
