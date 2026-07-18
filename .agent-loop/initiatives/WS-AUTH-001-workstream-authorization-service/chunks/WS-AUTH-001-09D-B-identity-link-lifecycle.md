# Chunk Contract: WS-AUTH-001-09D-B - Identity-Link Lifecycle And Race Closure

Initiative: `WS-AUTH-001` | Risk: L1 / P1 | Status: inactive

## Goal

Activate exact identity-link revoke/reactivate behavior and close the mixed
profile, link, and grant final-admin concurrency matrix.

## Start Gate

AUTH-09D-A must merge, signed memory must stop, and the user must explicitly
start this child. No implementation begins from the 09D-A branch.

## Allowed Boundary

This child may change actor/authorization/audit runtime, tests, API drill,
authorization docs, its initiative artifacts, and its one merge intent. It may
not add a migration, new link, replacement actor, compatibility path, service
admission, grant mutation, or consumer lifecycle behavior.

## Exact Surface

```text
POST /api/v1/actor-identity-links/{identity_link_id}/revoke
POST /api/v1/actor-identity-links/{identity_link_id}/reactivate
```

Both require effective system Access Administrator authority, the mutation
limiter, UUID `Idempotency-Key`, and the same strict normalized lifecycle reason
contract as 09D-A. Success and replay return exactly the typed link resource ID,
null version, and HTTP 200.

## Behavior Contract

- Active-link revoke writes caller, database time, and reason. A revoked link
  returns 409 `identity_link_already_revoked`.
- Revoked-link reactivate clears revoke fields; writes reactivation caller,
  database time, and reason; preserves its immutable issuer/subject binding; and
  returns 409 `identity_link_not_revoked` for an active link.
- A deactivated owning profile returns `actor_deactivated_terminal` and cannot
  regain an authenticatable link. A suspended profile may have its link repaired
  but remains unable to authenticate until separately reactivated.
- Human and fixed-service links are valid targets. Self-link revoke returns 403
  `resource_guard_denied`; a caller with a revoked own link cannot authorize its
  own reactivation.
- Link success evidence targets the exact link and also binds the owning target
  ActorProfile. Its invalidation obligation targets that ActorProfile authority
  projection. Reactivation is `effective=false -> effective=true`; revocation is
  `effective=true -> effective=false`.
- Link reactivation never restores a separately revoked AdminRoleGrant or
  ProjectRoleGrant and never advances target verification timestamps.
- Domain conflicts roll back the reservation and staged allow, commit one exact
  privacy-safe denial in a clean transaction, and do not consume the key.

## Concurrency Closure

All operations reuse 09D-A's reservation-first and singleton/caller-first lock
order. Real PostgreSQL tests cover revoke/reactivate, same-target different-key
races, profile/link loss, link/grant loss, and different-target final-admin loss.
At least one authenticatable effective Access Administrator remains after every
committed combination, and no test uses timing sleeps as lock evidence.

## Acceptance And Stop

Exactly two actions activate, producing the parent final totals of 65 actions,
17 active and 48 planned. Full replay, mismatch, conflict, rollback, timestamp,
privacy, rate/OpenAPI, manifest, coverage, and mixed-race matrices pass.

Stop after merge and signed memory. AUTH-09E requires a separate explicit start.
