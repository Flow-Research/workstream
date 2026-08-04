# Status: WS-QUAL-001 Backend Coverage Floor

## Current state

`WS-QUAL-001-PLAN2` merged through PR #260. `WS-QUAL-001-02R` merged through
PR #265 with all 2,996 exact-head tests passing and 21,004 / 23,455 statements
covered (89.550203 percent).

The current-main baseline after ART PR #268 is Backend run `30921410531` on
`5b853d50`: 3,068 tests completed, 21,453 / 23,938 statements covered
(89.619016 percent), 727.166 seconds hosted wall time, and a 567.994-second
slowest lane. The global CI floor remains 78 percent; named protected subsystem
checks remain blocking at 90 percent.

Historical QUAL work delivered the isolated database runner and test-integrity
guards through PRs #103, #105, and #108. The many stopped semantic-analysis
replacements remain historical evidence, not work to resume.

## Current gate

`WS-QUAL-001-03R` is the current implementation chunk. It must add meaningful
checker-owned behavior tests and gain at least 152 covered statements on the
current-main denominator to reach the 90.25-percent headroom target. The
focused test union measures
168 unique previously missing checker statements and projects 21,621 / 23,938,
or 90.320829 percent. Require Agent
Gates, CodeRabbit, all Backend semantic lanes, final coverage fan-in, six
internal reviewer tracks, and human review. An unexplained focused or hosted
runtime increase above 10 percent stops merge readiness.

The 94-case focused implementation selection passes in 37.76 seconds with
narrow checker-module coverage. The isolated full `test_checkers.py` run
reached the 1,200-second local ceiling after approximately 95 percent completion
with 163 passing tests and no failure output. It is not a complete pass; hosted
Backend remains mandatory.

## Stop condition

Planning does not change tests, application code, workflow code, or thresholds.
Do not raise the global floor until hosted combined coverage is at least 90.25
percent on the exact candidate head.
