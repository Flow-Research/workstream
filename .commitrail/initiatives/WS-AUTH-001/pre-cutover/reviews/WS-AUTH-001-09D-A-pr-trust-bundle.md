# WS-AUTH-001-09D-A PR Trust Bundle

## Chunk

`WS-AUTH-001-09D-A` - Profile Lifecycle And Evidence Repair

## Goal

Add exact administrative ActorProfile suspension, reactivation, and terminal
deactivation while repairing truthful lifecycle provenance and linked authority
evidence at the database boundary.

## Human-Approved Intent

The user explicitly started AUTH-09D. Required L1 review rejected the combined
parent contract before runtime edits and split it into 09D-A and separately
gated 09D-B. This PR implements only 09D-A.

## What Changed

- Added migration `0026_actor_profile_lifecycle` with profile reactivation
  provenance, API-equivalent whitespace normalization and 1-to-500-byte reason
  guards, fresh profile/link transition attribution, truthful reactivation
  direction, and fail-closed upgrade/downgrade checks.
- Added exact profile suspend, reactivate, and terminal deactivate routes using
  reservation-first idempotency, the central AUTH kernel, serialized authority
  locks, one route-owned commit, and bounded responses.
- Activated only the three profile lifecycle actions. Their exact owner is
  `WS-AUTH-001-09D-A`; both identity-link lifecycle actions remain planned under
  `WS-AUTH-001-09D-B`.
- Added behavior proof for privacy, evidence, rollback, fixed-service targets,
  failure injection, real PostgreSQL lock waits, migration refusal, OpenAPI,
  and the live API contract.

## Design Chosen

The route reserves its idempotency key before authorization, locks the authority
singleton and verified caller lineage before the exact target, revalidates the
current system grant, stages the profile transition and linked invalidation
evidence in one transaction, touches only the human caller, and commits once.
Missing targets and SQL failures roll back all staged evidence and state.

Reactivation provenance must be complete, non-null, and different from the
previous transition tuple. Deactivation is terminal. Fixed-service profiles may
be administrative targets, but this chunk never admits a service caller.

## Scope Control

Trusted main through REV PR #147 at `f18b620` is integrated. No identity-link
mutation route, service admission, feature-owned authorization, compatibility
alias, workflow, dependency, coverage threshold, or historical migration
changed.

## Tests And Checks Run

- Five exact isolated PostgreSQL migration nodes: passed in 250.95 seconds.
- Repaired constraint and dirty-row nodes: passed in 111.55 seconds, covering
  all 29 supported-runtime `str.strip()` whitespace code points and NBSP
  previous-head refusal.
- Historical rollback-guard cleanup and the immediately following migration
  node: passed together in 110.04 seconds.
- Expanded real lifecycle/service/failure matrix: passed in 100.36 seconds.
- PostgreSQL-observed concurrency node: passed in 140.69 seconds.
- Three historical owner-split migration nodes: passed in 199.52 seconds.
- Authorization coverage: 110 passed, 91.78 percent branch coverage.
- Actor coverage: 90.70 percent branch coverage.
- Lifecycle service: 100 percent branch coverage.
- Live HTTP API contract: passed.
- Repository-wide Ruff, stale scans, Markdown links, 87 Agent Gates,
  merge-intent validation, and diff integrity: passed.

## Test Delta

Tests assert exact action/permission/owner parity, normalized reason bounds,
API/database whitespace parity for all 29 supported-runtime points, fresh
transition provenance, denial privacy, service-target invariance, all nine
transaction failure stages, reusable failed idempotency keys, and actual
PostgreSQL waiter observation. No test was skipped, weakened, or rewritten to
conceal behavior.

## CI Integrity

The repository-wide 78 percent floor and focused 90 percent subsystem floors
remain unchanged. No workflow, dependency, threshold, skip, or exclusion was
modified. GitHub Backend remains authoritative for the full suite.

## Reviewer Results

Senior engineering, QA/test, security/auth, product/ops, architecture,
migration/data integrity, CI integrity, docs, reuse/dedup, and test delta all
pass exact integrated head `7c33e6453a2c91256c8fd416c63e30b95fd9d825`
after every valid finding was repaired.

## Remaining Risks

These system-authority routes intentionally change exact profile lifecycle
state and produce append-only authority evidence. PostgreSQL serialization and
database guards contain concurrent and direct-write risk. Identity-link state
can still make a reactivated profile unable to authenticate; that component
truth is deliberate and remains visible to later AUTH logic.

## Follow-Up Work

`WS-AUTH-001-09D-B` owns identity-link revoke/reactivate routes and mixed
profile/link/grant race closure only after this PR merges, trusted-main memory
passes, and the user gives a new explicit start. `WS-AUTH-001-09E` remains the
later fixed-service runtime-admission boundary.

## Human Review Focus

Review terminal deactivation, fresh reactivation provenance, denial privacy,
reservation and lock order, fixed-service non-admission, rollback atomicity,
exact child action ownership, and observed PostgreSQL waiter proof.

## Human Merge Ownership

The agent may publish and repair this branch but may not merge it. Only the
human may approve and merge the PR. Trusted-main automation owns post-merge
memory; 09D-B does not start automatically.
