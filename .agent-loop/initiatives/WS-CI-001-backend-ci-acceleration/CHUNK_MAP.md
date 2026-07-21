# CHUNK MAP: WS-CI-001

| Chunk | Title | Risk | Status |
| --- | --- | ---: | --- |
| `WS-CI-001-01` | Parallel Full-Suite Coverage | L1 | Completed and merged in PR #163 |
| `WS-CI-001-01R1` | Timeout Cleanup Repair | L1 | Completed and merged in PR #164 |
| `WS-CI-001-02` | Migrate-Once Backend Test Runtime | L1 | Source-level fixture consolidation in local verification; canonical start required before PR |

Each chunk maps to one PR. Chunk 01 introduced parallel coverage and chunk 01R1
repaired timeout cleanup. Measured evidence later proved that repeated per-test
migrations—not module assignment—were the primary bottleneck. The user directed
chunk 02 to fix that source problem locally and remove redundant sharding. It
must not be pushed or opened as a PR before canonical start and internal review.
