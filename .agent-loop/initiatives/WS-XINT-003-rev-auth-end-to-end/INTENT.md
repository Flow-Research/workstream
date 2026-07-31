# Intent: WS-XINT-003 REV-AUTH End-to-End Contract

## Problem being solved

Review and revision authority is currently described across `WS-REV-001`,
`WS-AUTH-001`, and `WS-XINT-002`. The individual declarations do not yet form
one reviewed, executable chain from review-policy configuration through queue
admission, lease-scoped judgment, revision submission, recovery, and release.

## Why this work matters

Review decisions determine whether entrusted contributor work is accepted,
returned for revision, or rejected. A missing or over-broad authorization seam
could expose submission artifacts, permit self-review, accept a stale decision,
erase a revision obligation, or attribute judgment to the wrong actor.

## Current behavior

- Project review and revision policy tables already exist.
- AUTH has planned action and permission rows for most REV operations; none of
  the review lifecycle actions is a complete active product surface.
- REV planning defines queue, lease, immutable Review/finding/resolution,
  revision preparation, FinalAcceptance, recovery, and release behavior.
- XINT-002 separately owns artifact review-packet materialization, evidence
  binding, and human-review submission-artifact preparation.
- REV-03P and AUTH-12D2 currently overlap in how policy persistence and mutation
  cutover are described and must be reconciled before implementation.

## Target behavior

Every review or revision operation uses one registered ActionId, one exact
human or fixed-service principal, a feature-owned canonical resource context,
and the existing opaque transaction-bound prepared-authorization protocol.
Authority is revalidated after final locks and decision evidence commits in the
same transaction as the protected mutation. No generic artifact read, inherited
uploader authority, token role, serialized handle, or independent REV-local
authorization path exists.

## Design chosen

Create one cross-initiative contract that inventories the complete surface,
settles ownership, and sequences narrow activation waves behind merged hidden
REV, ART, Task/Submission/Checker, and CON behavior. Registration remains
separate from activation and product route release.

## Alternatives considered

- Continue adding AUTH requirements to individual REV chunks: rejected because
  it repeats the ART-AUTH dependency failure and makes omissions likely.
- Put lifecycle rules in AUTH: rejected because AUTH evaluates authority and
  must not own Review, lease, finding, policy, revision, or contribution state.
- Let REV query grants directly: rejected because it creates a second policy
  engine and bypasses canonical denial evidence and revocation behavior.

## Boundaries preserved

- REV owns review/revision product semantics and canonical lifecycle rows.
- AUTH owns identity, permissions, candidates, evaluation, PREP custody, and
  authorization evidence.
- ART owns verified bytes, review packet materialization, and evidence binding.
- Task/Submission/Checker owners supply exact upstream and resubmission facts.
- CON owns contribution rules and conditional award persistence.
- The request route or service command owns the transaction and commits once.

## Expected risks

Self-review, stale leases, cross-project access, predecessor advancement,
revision-limit bypass, generic artifact access, service impersonation,
duplicate policy writers, partial decision/contribution commits, replay, and
operator recovery broadening.

## What must not change

- Stored Review decisions remain exactly `accept`, `needs_revision`, `reject`.
- Checker-caused `needs_revision` remains distinct from human Review revision.
- No adjudication, reputation mutation, frontend, or generic artifact-download
  authority is added.
- No compatibility path is retained for old token-role or local authorization.

## How this will be proven

Catalogue and surface parity, PostgreSQL concurrency and immutability tests,
crossed revocation/staleness races, exact-handle denial matrices, atomic
decision/CON rollback tests, fixed-service all-pairs denial, artifact access
tests, API contract drills, at least 90 percent changed-subsystem coverage, and
the hosted repository-wide coverage floor.

## Human decisions required

No new product decision is required to plan the dependency. Before runtime
implementation, the human must approve the reconciled chunk sequence and any
change to existing REV policy semantics.
