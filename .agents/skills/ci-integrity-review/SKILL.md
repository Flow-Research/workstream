---
name: ci-integrity-review
description: Review CI, lint, typecheck, test, coverage, workflow, and package-script changes for weakening or bypass behavior.
---

# CI Integrity Review

CI is the wall. It must not move to make the agent pass.

## Shared evidence

Use `reviewer-evidence-protocol` first. Bind the review to its exact target,
inspect relevant unchanged workflows and commands, replay prior findings,
separate executed from inspected evidence, state uncertainty and freshness, and
hand off non-CI findings without inventing another specialty's verdict.
Use canonical reviewer IDs from the initiative `REVIEWER_MATRIX.md` in handoffs.

## Inspect

- GitHub Actions or other CI workflows
- package scripts / Makefile / task runners
- test runner config
- lint config
- typecheck config
- coverage thresholds
- ignored paths
- skipped checks
- `|| true`, `continue-on-error`, `--passWithNoTests`, disabled failures

## Blockers

- Any weakening without explicit human approval.
- New skipped failures.
- Lowered coverage threshold.
- Removed lint/typecheck/test gate.
- Package script changed to hide errors.

## Completeness probe

Trace each required gate from trigger and path filter through job dependency,
command, exit propagation, artifact/coverage aggregation, and protected-branch
status. Probe cancellation, skipped-job, empty-selection, and rerun behavior;
green status alone is not proof that the intended command ran.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / FAIL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
CI files changed:
Integrity concerns:
Gate traceability and residual escape:
Required fixes:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
