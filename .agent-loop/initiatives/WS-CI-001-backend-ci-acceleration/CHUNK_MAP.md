# CHUNK MAP: WS-CI-001

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| `WS-CI-001-01` | Parallel Full-Suite Coverage | L1 | Completed and merged in PR #163 |
| `WS-CI-001-01R1` | Timeout Cleanup Repair | L1 | Completed and merged in PR #164 |
| `WS-CI-001-02` | Safe Routing, Cache, and Timing Refinement | L1 | Completed |
| `WS-CI-001-02A` | Safe Migrate-Once Database Reset | L1/P0 | Completed and merged |
| `WS-CI-001-02B` | Exact-Custody Semantic Test Lanes | L1/P0 | Completed and merged in PR #198 |
| `WS-CI-001-03` | Distributed Semantic Test Lanes | L1 | In implementation |

Each chunk maps to one PR. Chunk 01 preserves the full suite and every coverage
gate. Chunk 01R1 repaired timeout cleanup. Chunk 02 converts measured evidence
and PR #180 into two prospective implementation contracts. Chunk 02A first
proves the destructive reset and fixture migration under the existing CI
topology. Chunk 02B may then change runner/workflow topology using 02A evidence.
Chunk 03 preserves 02B's semantic ownership and evidence model while restoring
one hosted runner per lane and one fail-closed final required check.
