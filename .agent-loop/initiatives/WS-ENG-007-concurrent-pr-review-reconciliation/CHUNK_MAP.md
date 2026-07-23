# Chunk Map: WS-ENG-007 - Concurrent PR Review Reconciliation

| Order | Chunk | Purpose | Risk | State |
|---:|---|---|---:|---|
| 0 | `WS-ENG-007-00R1` | Repair planning-intake file/tree parity and recover PR #187 exactly once | L1/P0 | Emergency prerequisite review |
| 1 | `WS-ENG-007-01` | Add deterministic reviewed-patch identity and conservative base-delta review preservation | L1 | Blocked on 00R1 merge, signed reconciliation, and explicit start |
| 2 | `WS-ENG-007-02` | Add structured reviewer-track and upstream-finding reconciliation | L1 | Blocked on 01 merge and explicit start |
| 3 | `WS-ENG-007-03` | Add merge-group CI parity and queue-readiness proof | L1 | Blocked on 02 merge and explicit start |

Each chunk is one PR and stops after merge. Every successor requires a separate
explicit signed start.
