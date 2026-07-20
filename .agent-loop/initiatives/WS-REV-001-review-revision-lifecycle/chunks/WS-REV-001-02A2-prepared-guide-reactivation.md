# Chunk Contract: WS-REV-001-02A2 - Prepared Superseded Guide Reactivation

## Status

Proposed. Do not implement until every precondition merges and the user gives a
separate explicit start.

## Goal

Add intentional backward guide reactivation through the bodyless activation
command without exposing it under legacy local-role authorization or allowing a
delayed retry to replace a newer guide.

## Risk class

L1 privileged mutation, immutable provenance, and concurrency.

## Preconditions

- 02A1, 02A3, 02A4, and 08 are merged with Project-first locking, immutable activation sequence,
  pure decision/resource contracts, and
  unchanged superseded-candidate denial.
- Exact merged AUTH-PREP/custody and an AUTH-12 contract amendment are recorded
  by chunk ID, PR/SHA, typed action/resource contract, and tests. AUTH-12 runtime
  evaluator/cutover/activation has not run; `project.guide.activate` remains
  unavailable while this hidden behavior is built.
- A current-main contract refresh confirms route ownership and a separate human
  start.

## Acceptance boundary

- The route remains bodyless and accepts no caller reason.
- Superseded reactivation requires `If-Match` for the exact current active-guide
  ETag. Missing precondition is 428; stale/mismatched state is 412. Both leave
  guide/audit/AUTH feature state unchanged except AUTH-owned bounded denial
  evidence where its merged contract requires it.
- The command uses AUTH prepare/authority lock, then Project-first feature locks,
  final-fact recomposition, AUTH consume/evaluate once, shared audit flush, and
  one route-owned commit.
- Reactivation preserves the restored guide's original approver, effective time,
  and activation sequence; clears only its superseded time; supersedes the exact
  expected current guide at post-lock database time; and leaves exactly one
  active guide.
- Its migration amends the 02A3 database guard only for the exact prepared,
  If-Match-protected `superseded -> active` transition and corresponding
  `superseded_at -> NULL` and database-maintained update-time changes. ID,
  Project, version, content, summary, creator/creation time, original approver,
  effective time, and activation sequence remain immutable; every other change
  remains rejected.
- The shared AuditEvent records `project_guide_reactivated`, project/candidate,
  canonical actor, replaced/restored IDs and activation sequences,
  `older_guide_reactivated`, request/correlation IDs, AuthorizationDecision,
  and database time. Audit failure rolls back all feature mutation.
- Active repeat remains no-write idempotent. Draft first activation remains 02A3
  behavior. Unknown/cross-project/wrong-state targets fail closed.
- Independent-session tests cover competing reactivations, new activation versus
  reactivation, exact retry, delayed retry, current-guide change, authority loss,
  audit failure, and both commit orders.

## Required contract before start

The start refresh must add exact allowed/not-allowed files, verification
commands including focused/full coverage, required reviewers, merge intent, and
stop condition from then-current main. This proposed record is not implementation
authorization.

## Stop condition

After its future PR merges, stop. Its manifest gates AUTH-12; do not start 09A1
automatically.
