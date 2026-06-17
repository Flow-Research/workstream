---
name: ci-integrity-review
description: Review CI, lint, typecheck, test, coverage, workflow, and package-script changes for weakening or bypass behavior.
---

# CI Integrity Review

CI is the wall. It must not move to make the agent pass.

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

## Output

```text
Result: PASS / PASS WITH LOW RISKS / FAIL
CI files changed:
Integrity concerns:
Required fixes:
```
