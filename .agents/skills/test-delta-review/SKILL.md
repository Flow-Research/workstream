---
name: test-delta-review
description: Review changed tests for weakened assertions, removed coverage, skipped tests, and tests rewritten to match broken behavior.
---

# Test Delta Review

Review tests before trusting green checks.

## Shared evidence

Use `reviewer-evidence-protocol` first. Bind the review to its exact target,
inspect relevant unchanged tests and behavior owners, replay prior findings,
separate executed from inspected evidence, state uncertainty and freshness, and
hand off non-test findings without inventing another specialty's verdict.
Use canonical reviewer IDs from the initiative `REVIEWER_MATRIX.md` in handoffs.

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
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
Tests added:
Tests modified:
Tests removed/skipped:
Weakening concerns:
Required fixes:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
