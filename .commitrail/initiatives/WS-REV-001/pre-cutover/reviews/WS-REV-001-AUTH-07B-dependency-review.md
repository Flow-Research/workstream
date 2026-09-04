# Dependency Review: Merged AUTH-07B

> Historical evidence only. Merged AUTH-08 and AUTH-09A supersede this file's
> catalogue counts and future `57-to-61` arithmetic. Current gates derive exact
> counts from trusted main and keep all action activation custody in AUTH.

## Scope

Read-only review of merged AUTH-07B diff `e9d72a1..90eca12` and its impact on
the WS-REV plan. AUTH implementation remains owned by WS-AUTH.

## Confirmed Boundary

- `AuthorizationService.require(action_id, resource_context)` is request scoped,
  deny by default, bound to canonical actor state, and stages bounded audit
  evidence through the caller's `AsyncSession`.
- Only `actor.profile.read_self` and `actor.profile.update_self` are active.
- The catalogue contains 74 PermissionIds and 50 ActionIds: 2 active and 48
  planned. All 24 REV dependencies remain inactive; four are still absent.
- AUTH-08 remains unmerged. Its amended contract projects 57 ActionIds with 9
  active and 48 planned. The four later REV additions require exact 57-to-61
  parity, producing 9 active and 52 planned; none becomes active before its
  owning REV chunk.
- Actor self-update locks the identity link before the actor profile and
  revalidates lifecycle state in the mutation transaction.
- Token roles create no authority, unknown/planned actions fail closed, and
  unknown/unavailable public denials collapse to `permission_not_granted`.

## Findings

### High - Generic Teardown Commits Feature Work

`backend/app/api/deps/authorization.py::get_authorization_service` commits any
open shared-session transaction on successful dependency teardown. A future REV
route that stages work but intentionally defers or omits its explicit commit can
therefore be committed by AUTH. This violates caller-owned transaction
composition and makes correctness depend on FastAPI dependency teardown order.

Required AUTH repair: remove generic success auto-commit. Make each read or
mutation owner explicitly commit its business-plus-decision unit, and prove
forgotten/deferred commit rolls back rather than being committed by AUTH.

### Medium - Evidence SQL Failure Escapes As 500

An SQLAlchemy failure while `AuthorizationService.require` stages decision
evidence reaches the generic rollback/re-raise branch. Self-update happens to
catch the error in its route, but self-read exposes an unstructured 500 instead
of the stable retryable service-unavailable contract.

Required AUTH repair: translate decision-evidence persistence failure once at
the authorization composition boundary and test GET/PATCH rollback, no partial
evidence or profile mutation, stable 503 code, and retryability.

### Medium - Verification Timestamps Regress

The actor-self cutover resolves an existing actor through
`find_actor_for_authorization` and returns it without `_touch_verified_actor`.
Successful GET/PATCH requests therefore stop advancing
`ActorProfile.last_seen_at` and `ActorIdentityLink.last_verified_at`.

Required AUTH repair: define and restore the AUTH-owned timestamp semantics for
successful existing-actor access and add repeated API GET/PATCH regression tests
for both fields. REV does not prescribe whether timestamp staging precedes or
follows evaluation, or redefine lifecycle-denial timestamp behavior.

## REV Disposition

REV does not patch AUTH code. These repairs plus AUTH definition of done are a
hard gate in PLAN, CHUNK_MAP, RISKS, chunk 01 documentation adoption, first AUTH
consumer chunk 05, and final preflight chunk 13.

## Evidence

Current non-review initiative snapshot digest:
`8c67d1cd5610a99881e3085a332d25a5d307046ec68dd69e12a6b43f9046006b`.
The digest hashes sorted `sha256sum` output for initiative files excluding
`reviews/**`; it is a parked dependency-refresh snapshot, not the historical
PLAN publication evidence binding.

The historical PLAN evidence remains byte-for-byte bound to its pre-AUTH-08
reviewed SHA and therefore still records the old 50-to-54 assumption. It is not
current dependency evidence. After AUTH-08 and ART merge, final exact-SHA review
will replace that publication evidence with the merged 57-to-61 accounting.

```text
git show --check 90eca12
ruff check affected AUTH/actor/API files and focused tests: passed
focused authorization unit tests: 24 passed, 19 deselected
PR #130 Backend, Agent Gates, and CodeRabbit: passed before merge
```

Database integration was not rerun locally because the isolated database URL
was not configured. Merged PR evidence reports its PostgreSQL suite passed, but
that suite does not contain the three required regression proofs above.
