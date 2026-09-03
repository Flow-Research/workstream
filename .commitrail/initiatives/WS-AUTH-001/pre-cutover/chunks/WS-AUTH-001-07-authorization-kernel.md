# Parent Chunk: WS-AUTH-001-07 - Authorization Kernel And Permission Registry

## Status

Split before runtime implementation on 2026-07-15 after required L1 plan
review. No application or migration code was written under the combined
contract.

## Why the split was required

The combined contract crossed two independently reviewable persistence and
runtime boundaries:

- the closed permission/action catalogue and action-aware audit migration; and
- the deny-by-default evaluation kernel plus its first real API cutover.

It also proposed admin-definition and project-capability APIs before AUTH-08
and AUTH-10 create their authoritative grant sources. Implementing those APIs
in AUTH-07 would require fabricated grants, token-role authority, or deny-only
public surfaces. All three outcomes violate the adopted authorization design.

## Child chunks

| Chunk | Title | Boundary |
|---|---|---|
| `WS-AUTH-001-07A` | Closed Permission And Action Catalogue | Register exact approved permissions and planned actions, add action-aware audit parity, and make no action executable. |
| `WS-AUTH-001-07B` | Deny-By-Default Kernel And Self-Action Cutover | Implement the minimal kernel and activate only canonical actor self-read/self-update actions. |

## Deferred to owning chunks

- Permission and admin-role definition APIs move to AUTH-08, after bootstrap
  and administrative grants exist.
- Project-scoped authorization context moves to AUTH-10, after exact-project
  grants and canonical project capability composition exist.
- Feature resource loaders, grant matrices, concealment rules, and
  revoke-versus-command races remain with their owning cutover chunks.

## Ordering

`WS-AUTH-001-07A -> WS-AUTH-001-07B -> WS-AUTH-001-08`

Neither child starts the other automatically. Each child requires its own
evidence, internal review, PR, explicit human merge approval, signed merge
memory, and stop.
