---
name: test-delta-review
description: Review changed tests for weakened assertions, removed coverage, skipped tests, and tests rewritten to match broken behavior.
---

# Test Delta Review

Review tests before trusting green checks.

## Focus

For every changed test:

- Was the test strengthened or weakened?
- Was an assertion removed?
- Was a negative case removed?
- Was a failure condition skipped?
- Was behavior changed to match implementation instead of the requirement?
- Would this test fail on the old broken behavior?
- Are mocks hiding real behavior?

## Blockers

- Removed/skipped tests without explanation.
- Assertions weakened to match new behavior.
- Coverage lowered without approval.
- Bug fix without regression coverage when feasible.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / FAIL
Tests added:
Tests modified:
Tests removed/skipped:
Weakening concerns:
Required fixes:
```
