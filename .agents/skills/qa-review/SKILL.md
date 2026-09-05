---
name: qa-review
description: Review a diff for correctness, acceptance criteria coverage, edge cases, regressions, and missing tests.
---

# QA Review

Review current changes against the chunk contract.

## Shared evidence

Read `reviewer-evidence-protocol` first; it owns the exact target, prior findings,
executed from inspected evidence, uncertainty, freshness, traceability, and
verdict mechanics. Use canonical IDs from
`.ci/reviewer-evidence/REVIEWER_MATRIX.md` to hand off other specialties.
Apply this skill only to the assigned impact cone.

Simulate the pre-fix defect and require the named test to fail for the exact
behavior atom. Reject fixtures that abort before the intended assertion or
inputs the pre-fix code already rejects. These obligations are adopted through
the blind evaluation recorded by `WS-CI-005-03`.

## Focus

- Acceptance criteria coverage
- Missing behavior
- Edge cases
- Regression risks
- Incomplete tests
- Flaky assumptions
- Incorrect mocks
- Error states
- Canonical contract alignment and removal of superseded paths

## Rules

- Be concrete.
- Do not approve because code looks clean.
- Do not request broad rewrites unless necessary.
- Tie findings to acceptance criteria or observable behavior.
- Split compound criteria into behavior atoms. For each atom name the owner,
  implementation source, exact test, execution custody, and observed result.
- A test module name, broad command, or prose promise is not proof of every atom.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / BLOCKED / PROVISIONAL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
Covered criteria:
Missing criteria:
Atomic criterion-to-proof traceability:
residual escape hypothesis:
Findings:
Required fixes:
Suggested tests:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
