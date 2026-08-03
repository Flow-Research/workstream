# Status: WS-QUAL-001 Backend Coverage Floor

## Current state

`WS-QUAL-001-PLAN2` has reconciled the initiative against current `main` after
the documentation cleanup merged through PR #259. Deterministic documentation
checks and all required internal plan reviewers pass after scope, ownership,
contract, runtime, and historical-classification repairs. No QUAL implementation
chunk is active; PLAN2 awaits GitHub and human review.

The latest complete hosted baseline is 88.954981 percent across 23,368
statements and 2,914 tests. The global CI floor remains 78 percent. Multiple
named changed subsystems already have blocking 90-percent checks.

Historical QUAL work delivered the isolated database runner and test-integrity
guards through PRs #103, #105, and #108. The many stopped semantic-analysis
replacements remain historical evidence, not work to resume.

## Current gate

Merge PLAN2 after GitHub and human review. The first proposed implementation successor is
`WS-QUAL-001-02R`, limited to meaningful project/setup tests. It must be
refreshed on the then-current `main` before implementation.

## Stop condition

Planning does not change tests, application code, workflow code, or thresholds.
Do not raise the global floor until hosted combined coverage is at least 90.25
percent on the exact candidate head.
