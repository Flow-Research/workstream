# Chunk Contract: WS-XINT-003-03A — Reviewer Current-Work Read Activation

## Status and risk

Non-implementable planning skeleton after 02D. Refresh exact files and commands
on current main before an explicit user request. L1 reviewer authority and concurrency.

## Goal

Activate only concealed reviewer current-work through `review.queue.read`
against merged REV-05A/05B admission and server-selected current-work behavior.
Claim, release, decline, packet, artifact, and decision actions remain
unavailable.

## Allowed files

Enumerate exact AUTH evaluator/availability/parity and integrated test/evidence
files at current-main start. REV lifecycle files are read-only dependencies.

## Not allowed

New contexts/protocols/principals, REV lifecycle implementation, claim,
release, decline, packet/artifact, decision, revision, recovery, or route-release
behavior.

## Acceptance criteria

- Reviewer current-work returns exactly the active lease, one server-selected
  offer, or none. It never exposes the backlog. It requires an active exact-
  project reviewer grant and conceals self-authored submissions.
- Queue visibility does not imply claim or packet authority.
- Revocation, suspension, wrong project/role, self-review, stale admission, and
  crossed resource scope deny without disclosing backlog counts or identities.
- The chunk adds no ActionId, PermissionId, principal, context class, protocol,
  REV lifecycle behavior, or product route.

## Verification and reviewers

PostgreSQL concurrency, PREP denial, concealment, route parity, focused
90-percent coverage, hosted full coverage; architecture, security, product/ops,
QA, senior, reuse, docs, test-delta, and CI-integrity review.

## Stop

Merge and stop before claim activation.
