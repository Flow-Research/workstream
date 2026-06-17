---
name: qa-review
description: Review a diff for correctness, acceptance criteria coverage, edge cases, regressions, and missing tests.
---

# QA Review

Review current changes against the chunk contract.

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
Covered criteria:
Missing criteria:
Findings:
Required fixes:
Suggested tests:
```
