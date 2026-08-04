# Chunk Map: WS-QUAL-001 Backend Coverage Floor

## Historical completed work

| Chunk | Durable outcome | State |
|---|---|---|
| `WS-QUAL-001-PLAN` | Original 90-percent initiative plan | Merged PR #99; superseded by PLAN2 sequencing |
| `WS-QUAL-001-01` | Original combined harness/baseline contract | Superseded by the 01A/01B split before implementation |
| `WS-QUAL-001-01A` | Isolated least-privilege database runner | Merged PR #103 |
| `WS-QUAL-001-01B1A-R2` | Coverage configuration/evidence grammar | Merged PR #105 |
| `WS-QUAL-001-01B1B-R10` | Conservative test-weakening semantic guard | Merged PR #108 |

All other 01B/01B1/01B1A/01B1B replacement attempts are stopped historical
experiments. Do not resume them. `WS-QUAL-001-01B2` and the old 02-06 milestone
ladder are superseded before implementation.

## Current sequence

| Chunk | Purpose | Risk | State |
|---|---|---:|---|
| `WS-QUAL-001-PLAN2` | Reconcile current hosted baseline, retire obsolete machinery, and define the small closure sequence | L1 | Merged PR #260 |
| `WS-QUAL-001-02R` | Project/setup observable behavior coverage | L2 | Merged PR #265 |
| `WS-QUAL-001-03R` | Checker observable behavior coverage | L2 | Implementation in progress |
| `WS-QUAL-001-04R` | Change the exact global hosted CI floor from 78 to 90 after current-main proof | L1 | Proposed after measured >=90.25% proof |

One chunk maps to one PR. A test chunk may close early when its behavioral scope
is exhausted. The next contract refreshes from current `main`; stale missing-line
inventories are never implementation authority. If 02R and 03R are
insufficient, PLAN2 must be amended with one exact owner-specific successor;
there is no mixed residual-coverage chunk.
