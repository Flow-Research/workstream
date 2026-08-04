# Status: WS-QUAL-001 Backend Coverage Floor

## Current state

`WS-QUAL-001-PLAN2` merged through PR #260. `WS-QUAL-001-02R` is now at its
external-review gate with a test-only implementation and passing required
internal reviews.

The latest complete current-main hosted baseline is Backend run `30891776021`
on `b47a7e64`: 88.603709 percent across 23,455 statements and 2,936 tests.
02R's measured test union projects 21,004 covered statements, or 89.550203
percent. The global CI floor remains 78 percent; named protected subsystem
checks remain blocking at 90 percent.

Historical QUAL work delivered the isolated database runner and test-integrity
guards through PRs #103, #105, and #108. The many stopped semantic-analysis
replacements remain historical evidence, not work to resume.

## Current gate

Require Agent Gates, CodeRabbit, all Backend semantic lanes, final coverage
fan-in, and human review for `WS-QUAL-001-02R`. Hosted coverage must be at least
89.55 percent, and an unexplained hosted runtime increase above 10 percent
stops merge readiness.

## Stop condition

Planning does not change tests, application code, workflow code, or thresholds.
Do not raise the global floor until hosted combined coverage is at least 90.25
percent on the exact candidate head.
