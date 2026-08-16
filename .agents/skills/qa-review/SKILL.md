---
name: qa-review
description: Review a diff for correctness, acceptance criteria coverage, edge cases, regressions, and missing tests.
---

# QA Review

Review current changes against the chunk contract.

## Shared evidence

Use `reviewer-evidence-protocol` first. Bind the review to its exact target,
inspect relevant unchanged behavior and tests, replay prior findings, separate
executed from inspected evidence, state uncertainty and freshness, and hand off
non-QA findings without inventing another specialty's verdict.
Use canonical reviewer IDs from the initiative `REVIEWER_MATRIX.md` in handoffs.

## Focus

- Acceptance criteria coverage
- Missing behavior
- Edge cases
- Regression risks
- Incomplete tests
- Flaky assumptions
- Incorrect mocks
- Error states
- Backward compatibility

## Rules

- Be concrete.
- Do not approve because code looks clean.
- Do not request broad rewrites unless necessary.
- Tie findings to acceptance criteria or observable behavior.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / FAIL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
Covered criteria:
Missing criteria:
Findings:
Required fixes:
Suggested tests:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
