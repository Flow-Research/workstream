# Status: WS-QUAL-001 Behavior And Mutation Assurance

## Current state

Coverage closure through `WS-QUAL-001-03R` is complete. PR #269 merged at
`5f2baf90`; main Backend run `30926337804` completed all 3,162 tests and
reported 21,620 / 23,938 statements (90.316651 percent), 620.264 seconds hosted
wall time, and a 464.471-second slowest lane.

The global blocking floor remains 78 percent by explicit human decision. Named
new or materially changed subsystem checks remain blocking at 90 percent.

## Mutation-gate disposition

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

The subsequent blocking rollout proved unsuitable for ordinary work: its
callable-wide selection treated unchanged executable lines as part of every
small changed declaration and produced unresolvable survivor sets. The hosted
workflow is therefore retired pending a separately reviewed changed-line-aware
design. Existing policy and evidence files remain historical input, not an
active PR requirement.

Existing Backend semantic lanes, global 78-percent coverage, protected
90-percent subsystem floors, lint, and review gates remain unchanged and
blocking on their existing terms.

## Stop condition

Do not restart mutation enforcement without a fresh bounded plan and proof that
unchanged executable lines cannot block a declaration-only change.
