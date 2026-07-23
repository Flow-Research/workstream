# Chunk Map: WS-ENG-007 - Concurrent PR Review Reconciliation

| Order | Chunk | Purpose | Risk | State |
|---:|---|---|---:|---|
| 0 | `WS-ENG-007-00R1` | Repair planning-intake file/tree parity and recover PR #187 exactly once | L1/P0 | Merged; recovery superseded after rerun-cardinality failure |
| 0 | `WS-ENG-007-00R2` | Canonicalize repeated trusted check evidence and reconcile PRs #187 and #188 exactly once | L1/P0 | Merged; superseded by mutable-history failure |
| 0 | `WS-ENG-007-00R3` | Freeze accepted checks at merge time and give explicit starts deterministic recovery parity | L1/P0 | Merged; exposed cross-initiative projection mixing |
| 0 | `WS-ENG-007-00R4` | Separate global merge evidence from initiative-local authority projections | L1/P0 | Active fail-closed recovery after the first cross-initiative start exposed projection mixing |
| 1 | `WS-ENG-007-01` | Add deterministic reviewed-patch identity and conservative base-delta review preservation | L1 | Blocked on 00R4 merge, successful reconciliation, and explicit start |
| 2 | `WS-ENG-007-02` | Add structured reviewer-track and upstream-finding reconciliation | L1 | Blocked on 01 merge and explicit start |
| 3 | `WS-ENG-007-03` | Add merge-group CI parity and queue-readiness proof | L1 | Blocked on 02 merge and explicit start |

Recovery chunks are exceptional ordered prerequisites; `00R4` preserves the
merge-bound evidence fixed by `00R3` while repairing cross-initiative authority
projection composition. Implementation chunks
remain one PR each and stop after merge. Every successor requires a separate
explicit signed start.
