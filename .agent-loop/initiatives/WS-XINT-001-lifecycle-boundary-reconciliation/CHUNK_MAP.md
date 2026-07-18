# Chunk Map: WS-XINT-001 Lifecycle Boundary Reconciliation

This initiative contains one planning PR. Runtime work remains in the four
owning initiatives and requires separate chunk contracts, review, and explicit
human starts.

| Chunk | Purpose | Risk | Status |
|---|---|---:|---|
| `WS-XINT-001-PLAN` | Reconcile AUTH, ART, REV, and CON ownership, activation, transactions, and handoffs | L1 | Active after explicit user start |

## Downstream owner handoffs

| Handoff | Required owner response |
|---|---|
| AUTH <-> ART | AUTH amends activation custody/service-action contracts; ART amends its future chunk sequencing |
| ART <-> REV | ART defines narrow review capabilities; REV consumes them without provider or repository access |
| AUTH <-> REV | AUTH owns registration/evaluators/activation; REV owns hidden lifecycle behavior and resource facts |
| REV/AUTH <-> CON | REV invokes a CON transaction participant; core creation makes no ART call and CON owns its public/action surfaces |
| AUTH roles/services -> all owners | AUTH removes the combined project role, adds fixed service runtime admission, and each feature consumes only its exact grant or service path |

No row above is a same-initiative successor. Merge intent therefore names no
successor; the user owns parallel work-queue priority.
