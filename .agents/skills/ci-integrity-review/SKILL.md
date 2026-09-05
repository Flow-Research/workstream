---
name: ci-integrity-review
description: Review CI, lint, typecheck, test, coverage, workflow, and package-script changes for weakening or bypass behavior.
---

# CI Integrity Review

CI is the wall. It must not move to make the agent pass.

## Shared evidence

Read `reviewer-evidence-protocol` first; it owns the exact target, prior findings,
executed from inspected evidence, uncertainty, freshness, traceability, and
verdict mechanics. Use canonical IDs from
`.ci/reviewer-evidence/REVIEWER_MATRIX.md` to hand off other specialties.
Apply this skill only to the assigned impact cone.

Trace actual infrastructure custody through selected tests, services or
PostgreSQL, sessions, artifacts, coverage, aggregation, and required status.
Green status or a command label alone is not custody. These obligations are
adopted through the blind evaluation recorded by `WS-CI-005-03`.

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
Result: PASS / PASS WITH LOW RISKS / BLOCKED / PROVISIONAL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
CI files changed:
Integrity concerns:
Gate traceability and residual escape:
Required fixes:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
