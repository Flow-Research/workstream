# Status: WS-QUAL-001 Behavior And Mutation Assurance

## Current state

Coverage closure through `WS-QUAL-001-03R` is complete. PR #269 merged at
`5f2baf90`; main Backend run `30926337804` completed all 3,162 tests and
reported 21,620 / 23,938 statements (90.316651 percent), 620.264 seconds hosted
wall time, and a 464.471-second slowest lane.

The global blocking floor remains 78 percent by explicit human decision. Named
new or materially changed subsystem checks remain blocking at 90 percent.

## Current gate

`WS-QUAL-001-PLAN3` is planning only. It replaces the unstarted 04R global-floor
switch with a two-stage behavior/mutation assurance proposal:

1. `04M` — bounded, pinned, changed-scope mutation pilot with complete evidence
   and no blocking score.
2. Human calibration checkpoint.
3. `05M` — separately approved blocking survivor policy for eligible changed
   logic and explicit test-only behavior claims.

No mutation dependency, workflow, policy script, or blocking check has been
implemented.

## Stop condition

Stop after PLAN3 planning review and PR. Do not start 04M automatically. Do not
start 05M without accepted exact hosted pilot evidence and a new human
instruction.
