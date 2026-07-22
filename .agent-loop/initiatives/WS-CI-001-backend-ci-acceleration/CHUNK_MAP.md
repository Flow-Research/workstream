# CHUNK MAP: WS-CI-001

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| `WS-CI-001-01` | Parallel Full-Suite Coverage | L1 | Completed and merged in PR #163 |
| `WS-CI-001-01R1` | Timeout Cleanup Repair | L1 | Implemented and internally reviewed; awaiting hosted repair PR proof/human review |
| `WS-CI-001-02` | Safe Routing, Cache, and Timing Refinement | L1 | Future; not started and requires separate approval |

Each chunk maps to one PR. Chunk 01 preserves the full suite and every coverage
gate. Chunk 01R1 is the bounded post-merge response to CodeRabbit's timeout
cleanup finding. Chunk 02 may be planned only from measured 01 evidence and
cannot be activated without separate human approval.
