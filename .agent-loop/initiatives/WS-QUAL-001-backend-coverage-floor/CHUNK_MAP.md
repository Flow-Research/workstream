# Chunk Map: WS-QUAL-001 Backend Coverage Floor

| Chunk | Scope | Risk | State |
|---|---|---:|---|
| `WS-QUAL-001-01` | Combined harness/baseline contract | L1 | Split after circuit-breaker review |
| `WS-QUAL-001-01A` | Isolated least-privilege database runner and two-phase complete-suite CI | L1 | Merged through PR #103 as `2901a3e` |
| `WS-QUAL-001-01B` | Combined coverage policy, baseline, and CI ratchet | L1 | Circuit breaker triggered at 480/500 before required proof; split proposed |
| `WS-QUAL-001-01B1` | Combined parser and semantic-delta policy core | L1 | Blocked at 496/500 after two repair cycles; superseded by 01B1A/01B1B |
| `WS-QUAL-001-01B1A` | Read-only coverage arithmetic and bounded policy parsers | L1 | Blocked at 394/400 after two parser repair cycles |
| `WS-QUAL-001-01B1A-R1` | Replacement parser candidate closing two normalization bypasses | L1 | Stopped at `c0fa4a2`; superseded by R2 |
| `WS-QUAL-001-01B1A-R2` | Canonical coverage.py exclusion grammar closure | L1 | Merged through PR #105 as `8a4182e` |
| `WS-QUAL-001-01B1B` | Repository-delta and semantic test-integrity guards | L1 | Blocked at 223/300 after two binding repair cycles |
| `WS-QUAL-001-01B1B-R1` | Lexical binding closure for semantic guards | L1 | Stopped at first size checkpoint; superseded by R2 |
| `WS-QUAL-001-01B1B-R2` | Measured lexical binding closure | L1 | Blocked at 348/350 after cycle-zero proof-fit failure |
| `WS-QUAL-001-01B1B-R3` | Stdlib symtable lexical closure | L1 | Blocked at 468/500 before cycle-one repair |
| `WS-QUAL-001-01B1B-R4` | Complete symtable control/value flow | L1 | Blocked at 535/550 after cycle-zero review |
| `WS-QUAL-001-01B1B-R5` | Single-pass abstract flow closure | L1 | Blocked at 641/650 after cycle-zero review |
| `WS-QUAL-001-01B1B-R6` | Transitive provenance closure | L1 | Blocked at 800/800 after cycle-one review |
| `WS-QUAL-001-01B1B-R7` | Recursive iterable provenance | L1 | Stopped after final two-cycle review; do not resume |
| `WS-QUAL-001-01B1B-R8` | Conservative syntactic integrity policy | L1 | Stopped after final review found Python 3.11 scope incompatibility |
| `WS-QUAL-001-01B1B-R9` | Python 3.11 comprehension scope compatibility | L1 | Stopped after final Python 3.13 TypeVar child-order finding |
| `WS-QUAL-001-01B1B-R10` | Python 3.13 TypeVar child order | L1 | Merged through PR #108 as `5c47aba` |
| `WS-QUAL-001-01B2` | Git provenance, configured baseline evidence, and CI ratchet | L1 | Inactive pending explicit user start |
| `WS-QUAL-001-02` | Project setup/policy/correction service coverage; floor at least 82% | L1 | Inactive |
| `WS-QUAL-001-03` | Project repository/router coverage; floor at least 84% | L1 | Inactive |
| `WS-QUAL-001-04` | Task service/repository/router coverage; floor at least 86% | L1 | Inactive |
| `WS-QUAL-001-05` | Checker service/runner/repository/router/worker coverage; floor at least 88% | L1 | Inactive |
| `WS-QUAL-001-06` | Enumerated residual gaps and permanent 90% CI floor | L1 | Inactive |

Each coverage-test chunk is limited to 500 implementation lines, except the
reviewed chunk-01A genuine-proof exception capped at 700. Missing its numeric
floor or size budget stops the chunk for replanning;
scope does not spill into the next chunk. A later chunk may start only after the
prior PR merges, post-merge evidence plus initiative `STATUS.md` and global
`LOOP_STATE.md`, `WORK_QUEUE.md`, and `REVIEW_LOG.md` are updated and merged,
and the user provides a new start signal.
