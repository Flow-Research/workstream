# Chunk Map: WS-QUAL-001 Behavior And Mutation Assurance

## Completed and superseded work

| Chunk | Durable outcome | State |
|---|---|---|
| `WS-QUAL-001-PLAN` | Original coverage initiative plan | Merged PR #99; superseded |
| `WS-QUAL-001-01A` | Isolated least-privilege database runner | Merged PR #103 |
| `WS-QUAL-001-01B1A-R2` | Coverage configuration/evidence grammar | Merged PR #105 |
| `WS-QUAL-001-01B1B-R10` | Conservative test-weakening guard | Merged PR #108 |
| `WS-QUAL-001-PLAN2` | Current-main coverage closure plan | Merged PR #260; succeeded by PLAN3 |
| `WS-QUAL-001-02R` | Project/setup observable behavior coverage | Merged PR #265 |
| `WS-QUAL-001-03R` | Checker observable behavior coverage | Merged PR #269; main at 90.316651% |
| `WS-QUAL-001-04R` | Raise global floor from 78 to 90 | Superseded before implementation; 78 retained by human decision |

All other old 01B/01B1 replacement attempts and the old 02-06 milestone ladder
remain stopped historical experiments. Do not resume them.

## Current sequence

| Chunk | Purpose | Risk | State |
|---|---|---:|---|
| `WS-QUAL-001-PLAN3` | Replace percentage-only closure with behavior/mutation assurance | L1 | Planning in progress |
| `WS-QUAL-001-04M` | Pilot pinned changed-scope mutation evidence without a score gate | L1 | Proposed after PLAN3 merge and explicit instruction |
| `WS-QUAL-001-05M` | Add calibrated blocking behavior-mutation policy | L1 | Proposed only after accepted 04M hosted evidence and explicit instruction |

## Dependency rule

`PLAN3 -> 04M -> human calibration checkpoint -> 05M`.

Each chunk maps to one PR. `04M` may prove that the candidate engine or target
strategy is unsuitable and stop without `05M`. Planning does not pre-authorize
either implementation chunk.
