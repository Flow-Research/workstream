# Status: WS-QUAL-001 Behavior And Mutation Assurance

## Current state

Coverage closure through `WS-QUAL-001-03R` is complete. PR #269 merged at
`5f2baf90`; main Backend run `30926337804` completed all 3,162 tests and
reported 21,620 / 23,938 statements (90.316651 percent), 620.264 seconds hosted
wall time, and a 464.471-second slowest lane.

The global blocking floor remains 78 percent by explicit human decision. Named
new or materially changed subsystem checks remain blocking at 90 percent.

## Current gate

`WS-QUAL-001-PLAN3` merged through PR #272. Its planning-only correction
`WS-QUAL-001-PLAN3R1` merged through PR #278 after resolving all late CodeRabbit
findings.

`WS-QUAL-001-04P` merged through PR #281 and established the protected, exactly
pinned, hash-verified mutation dependency authority.

`WS-QUAL-001-04M` is implemented and internally reviewed. Its rebased exact-head
local pilot at `f8b59eec` completed in 254.672 seconds with 1,091 generated
mutants fully reconciled: 84 killed, 59 survived, 948 excluded, and zero error,
timeout, or suspicious outcomes. Strong calibration killed two representative
mutants and deliberately weak calibration left two alive. The focused policy
module is at 90.11 percent coverage. Hosted PR-head evidence remains required
before the human calibration checkpoint.

The corrected proposal remains two-stage:

1. `04M` — bounded, pinned, changed-scope mutation pilot with complete evidence
   and no blocking score.
2. Human calibration checkpoint.
3. `05M` — separately approved blocking survivor policy for eligible changed
   logic and explicit test-only behavior claims.

The mutation score remains observational. Existing Backend semantic lanes,
global 78-percent coverage, and protected 90-percent subsystem floors remain
unchanged and blocking on their existing terms.

## Stop condition

Stop after the 04M review and PR. Do not start 05M without accepted exact hosted
pilot evidence, a human calibration checkpoint, and a new human instruction.
