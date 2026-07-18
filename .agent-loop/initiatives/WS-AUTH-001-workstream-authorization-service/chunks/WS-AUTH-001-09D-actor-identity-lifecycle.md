# Parent Chunk: WS-AUTH-001-09D - Actor And Identity-Link Lifecycle Mutations

Status: split before runtime implementation by required L1 plan review on
2026-07-18.

## Goal

Provide irreversible, idempotent, audited actor and identity-link lifecycle
administration without losing the final authenticatable Access Administrator.

## Why This Parent Was Split

The inherited contract combined five routes, a PostgreSQL evidence repair,
profile schema provenance, two resource families, and all mixed final-admin
races. Required review found that it also contradicted the implemented
reservation order, lacked a public lifecycle response, and could not represent
truthful reactivation invalidation.

No runtime code was changed under the rejected parent contract.

## Children

| Chunk | Scope | Gate |
|---|---|---|
| `WS-AUTH-001-09D-A` | Shared typed/PostgreSQL lifecycle evidence parity, profile reactivation provenance, and profile suspend/reactivate/deactivate | Active after the user's 09D start and repaired-contract review |
| `WS-AUTH-001-09D-B` | Identity-link revoke/reactivate plus mixed profile/link/grant final-admin race closure | Inactive until 09D-A merge, signed memory, and a separate explicit start |

## Shared Invariants

- Only effective system-scoped Access Administrators mutate lifecycle state.
- Reservation is the first database write. Current authority is revalidated
  before replay or mismatch is disclosed.
- Every lifecycle mutation uses `AuthorityControl(id=1)` before serialized
  caller and target locks. The singleton serializes every final-admin-affecting
  path, so no competing mutation uses a different authority lock order.
- Deactivation is terminal. Reactivation never restores a revoked grant.
- State, success evidence, one invalidation obligation, and idempotency
  completion commit once in the route-owned transaction.
- Consumer task/review state, service admission, grants, and assignments are not
  mutated by either child.

## Stop Condition

Each child stops after merge and signed memory. `WS-AUTH-001-09E` remains
inactive until both children merge and the user gives a separate explicit
start.
