# CHUNK MAP: WS-CI-001

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| `WS-CI-001-01` | Parallel Full-Suite Coverage | L1 | Completed and merged in PR #163 |
| `WS-CI-001-01R1` | Timeout Cleanup Repair | L1 | Completed and merged in PR #164 |
| `WS-CI-001-02` | Semantic-Lane Planning Amendment | L1 | Active signed planning chunk; implementation prohibited |
| `WS-CI-001-02A` | Migrate-Once Semantic Test Lanes | L1/P0 | Proposed successor; requires separate signed implementation start |

Each chunk maps to one PR. Chunk 01 preserves the full suite and every coverage
gate. Chunk 01R1 repaired timeout cleanup. Chunk 02 converts measured evidence
and PR #180 into a prospective implementation contract. Only 02A may adopt the
implementation, after this planning PR merges and 02A receives a signed start.
