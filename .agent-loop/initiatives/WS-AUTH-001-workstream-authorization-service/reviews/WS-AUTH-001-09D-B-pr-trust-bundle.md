# WS-AUTH-001-09D-B PR Trust Bundle

## Chunk

`WS-AUTH-001-09D-B` - Identity-Link Lifecycle And Race Closure

## Goal

Let an effective system Access Administrator revoke or reactivate an exact
human or fixed-service identity link while preserving current authority,
privacy, final-administrator safety, idempotency, and atomic evidence.

## Changes

- Added strict idempotent revoke and reactivate endpoints for an exact
  ActorIdentityLink.
- Activated only the two matching ActionIds and PermissionIds; the catalogue is
  65 actions with 17 active and 48 planned.
- Reused centralized authorization, profile/link/grant locking, lifecycle
  guards, evidence, invalidation, idempotency, limiter, and route-owned commit.
- Added exact state, attribution, replay, mismatch, conflict, rollback,
  timestamp, privacy, API, OpenAPI, and real PostgreSQL concurrency proof.
- Corrected the AUTH plan so an inactive contributor foundation follows 09D-B
  and AUTH-13/14 consume its `contributor_id` fields rather than rename them
  later.

## Boundary

This PR does not add a migration, fixed-service token admission, grant
mutation, service assignment, project authorization cutover, feature action,
compatibility route, fallback, or legacy response. Reactivating a link restores
neither an AdminRoleGrant nor service admission. Deactivated actors remain
terminal, suspended actors remain unable to authenticate, and target
verification timestamps do not advance.

## Design

Each new request validates and freezes its body, reserves idempotency, then
authorizes before target disclosure. AUTH locks the singleton authority
control, caller profile/link/grant, and target profile/link/grant in the
canonical order. State, caller touch, success evidence, ActorProfile
invalidation, idempotency completion, and commit are one transaction. Expected
domain conflicts are restaged as one privacy-safe denial after rollback; SQL or
evidence failures return the stable retryable 503 with no partial state.

## Proof

- Mandatory PostgreSQL lifecycle/concurrency nodes: 2 passed in 241.09 seconds.
- Isolated authorization behavior and coverage selection: 112 passed in 543.89
  seconds at 90.11 percent branch coverage.
- ART-integrated focused PostgreSQL selection: 167 passed in 299.64 seconds.
- Direct route outcome matrix: 5 passed, covering success, replay, mismatch,
  conflict, and retryable SQL failure with exact transaction ordering.
- Isolated real HTTP API contract drill: passed.
- Ruff, stale Workstream, authorization, and artifact scans, Markdown links,
  all 88 agent
  gates, merge-intent validation, and diff integrity: passed.
- No skips, xfails, threshold reductions, or workflow-gate weakening.

Exact reviewed code SHA
`ab6669ebde0d5947ab8b4631667c9ec552ba7687` against trusted main
`1b5422fcaa361152af7c2b1f82a763d99c0e6db5` passed senior engineering,
QA/test, security/auth, product/ops, architecture, CI integrity, docs,
reuse/dedup, and test-delta review after every valid finding was repaired.

## External CI Repair

The old PR head passed 1,334 Backend tests at 85.09 percent repository-wide
coverage, then failed the unchanged authorization floor at 89.39 percent. The
repair adds no exclusion, skip, xfail, threshold change, or production branch.
Its five behavior cases execute 29 lifecycle-route statements that the old
full-suite dataset did not count, exceeding the measured 12-statement deficit.
Replacement GitHub Backend remains the authoritative final percentage.

## Reviewer Results

| Track | Result | Blocking findings |
|---|---|---|
| Senior engineering | PASS AFTER FIXES | none |
| QA/test | PASS AFTER FIXES | none |
| Security/auth | PASS AFTER FIXES | none |
| Product/ops | PASS AFTER FIXES | none |
| Architecture | PASS AFTER FIXES | none |
| CI integrity | PASS AFTER FIXES | none |
| Docs | PASS AFTER FIXES | none |
| Reuse/dedup | PASS AFTER FIXES | none |
| Test delta | PASS AFTER FIXES | none |

## Findings Closed

The review loop repaired real lock observation, exact race outcomes, complete
rollback snapshots, denial and replay timestamp assertions, merge-intent and
documentation gaps, stale migration reservations, contributor-foundation
scope, and contradictory lifecycle-state wording. No production compatibility
path or broader authority was introduced. ART-main reconciliation then fixed
stale shared-state assertions and exact action arithmetic; the CI repair added
only genuine route behavior coverage.

## Follow-up

The immutable schema-v2 merge intent names
`WS-AUTH-001-CONTRIBUTOR-FOUNDATION` as the same-initiative successor. That
chunk will clean-cut TaskAssignment and Submission ownership to
`contributor_id`, add database-backed canonical-human lineage, and expose
transaction-local active-human revalidation. It remains inactive until 09D-B
merges, signed automated memory passes, and the user explicitly starts it.
AUTH-09E and all later consumers remain separate gates.

## Human Review Focus

Review authorization-before-disclosure, canonical lock order, final-admin
preservation, replay after later state changes, privacy-safe denial evidence,
atomic rollback, absence of grant/service restoration, and the inactive
contributor-foundation boundary.

## Merge Ownership

The agent may publish and repair this branch but may not merge it. Only the
human may approve this PR for merge. After merge, trusted-main automation owns
schema-v2 memory generation; no manual post-merge memory PR should be opened if
that workflow succeeds.
