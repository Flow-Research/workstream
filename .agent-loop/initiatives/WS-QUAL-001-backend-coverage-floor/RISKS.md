# Risks: WS-QUAL-001 Behavior And Mutation Assurance

| Risk | Consequence | Control |
|---|---|---|
| Full-repository mutation | CI becomes unusably slow | Mutate only eligible changed or explicitly claimed targets under hard limits |
| Equivalent/noisy mutants | Correct PRs are blocked without quality benefit | Non-blocking pilot, typed classifications, separate human checkpoint before enforcement |
| Score gaming | Contributors kill one easy mutant or raise a percentage while behavior remains weak | Survivor-based exact evidence; no “one mutant” or global score success rule |
| Target-selection escape | Important changed logic is silently omitted | Workstream-owned deterministic diff/claim parser; missing or broad evidence fails closed |
| Test-selection escape | Mutants pass because relevant tests were not selected | Bind explicit owning nodes, baseline-run them first, validate selection in policy tests |
| Test-only coverage padding | No production diff means no mutation work | Require bounded production targets for test-only behavior/coverage claims |
| Timeout treated as success | Hanging mutants silently pass | Timeout is a distinct non-killed outcome and blocks in enforcement mode |
| Cache poisoning/staleness | Results do not describe the current source | Bind tree, config, tool, targets, tests, and result digests; cache is acceleration only |
| Mutation exclusions spread | Meaningful behavior is hidden | No source pragmas in pilot; classifications are narrow, typed, reviewed evidence |
| Dependency compromise | CI executes an untrusted tool closure | Exact pin and hash-lock the development-only dependency closure |
| Worktree mutation | Contributor source is left modified | Execute in disposable isolated workspace and verify tree custody |
| Existing gates weakened | Mutation becomes a substitute for real tests | Preserve semantic lanes, full suite, API E2E, 78 global and protected 90 floors |
| Runtime critical-path increase | Contribution slows despite scoped execution | Independent job, 12-minute command/15-minute job bounds, <=2-minute critical-path objective |
| Production defect discovered | QUAL scope drifts into product repair | Stop and hand the defect to its owning initiative |

No secret, production credential, production data, payment, or deployment
access is required. The CI dependency and executable-tool boundary requires
security and CI-integrity review.
