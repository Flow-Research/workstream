# CHUNK MAP: WS-CI-001

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| `WS-CI-001-01` | Parallel Full-Suite Coverage | L1 | Completed and merged in PR #163 |
| `WS-CI-001-01R1` | Timeout Cleanup Repair | L1 | Completed and merged in PR #164 |
| `WS-CI-001-02` | Semantic-Lane Planning Amendment | L1 | Active signed planning chunk; implementation prohibited |
| `WS-CI-001-02A` | Safe Migrate-Once Database Reset | L1/P0 | Proposed successor; requires separate signed implementation start |
| `WS-CI-001-02B` | Exact-Custody Semantic Test Lanes | L1/P0 | Proposed after 02A evidence; not yet eligible to start |

Each chunk maps to one PR. Chunk 01 preserves the full suite and every coverage
gate. Chunk 01R1 repaired timeout cleanup. Chunk 02 converts measured evidence
and PR #180 into two prospective implementation contracts. Chunk 02A first
proves the destructive reset and fixture migration under the existing CI
topology. Chunk 02B may then change runner/workflow topology using 02A evidence.
Only 02A is the declared successor of this planning PR.
