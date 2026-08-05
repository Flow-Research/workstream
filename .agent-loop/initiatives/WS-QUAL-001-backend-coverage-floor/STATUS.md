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

`WS-QUAL-001-04M` merged through PR #285 as `7f395d47`. Its final exact-head
hosted pilot on `0c25acec8fb3326e68169512e829711a0790b190` completed mutation
execution in 34.886 seconds and the hosted job in 53 seconds. It reconciled
2,493 generated mutants: 149 killed, 89 survived, 2,255 excluded, and zero
error, timeout, or suspicious outcomes. Strong calibration killed two
representative mutants and the deliberately weak calibration left two alive.
The human accepted this evidence and explicitly started `WS-QUAL-001-05M`.

The corrected proposal remains two-stage:

1. `04M` — merged bounded, pinned, changed-scope mutation pilot with complete
   evidence and no blocking score.
2. Human calibration checkpoint — accepted.
3. `05M` — implemented and internally reviewed bounded blocking survivor
   policy for eligible changed logic and explicit test-only behavior claims;
   exact-head hosted CI and external review remain before human merge.

The mutation score remains observational. Existing Backend semantic lanes,
global 78-percent coverage, and protected 90-percent subsystem floors remain
unchanged and blocking on their existing terms.

## Stop condition

Stop after the 05M PR is merge-ready. Do not start another QUAL chunk.
