---
name: test-delta-review
description: Review changed tests for weakened assertions, removed coverage, skipped tests, and tests rewritten to match broken behavior.
---

# Test Delta Review

Review tests before trusting green checks.

## Shared evidence

Read `reviewer-evidence-protocol` first; it owns the exact target, prior findings,
executed from inspected evidence, uncertainty, freshness, traceability, and
verdict mechanics. Use canonical IDs from
`.ci/reviewer-evidence/REVIEWER_MATRIX.md` to hand off other specialties.
Apply this skill only to the assigned impact cone.

Compare the changed test with the pre-fix defect and require a discriminating
assertion. Reject setup-only failures, vacuous inputs, and tests that already
passed against the broken implementation. These obligations are adopted through
the blind evaluation recorded by `WS-CI-005-03`.

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

## Completeness probe

Map each changed or claimed behavior atom to the exact assertion that would fail
if that atom regressed. Check actor/resource/state/failure variants separately,
and compare with the old behavior. A test name without a discriminating
assertion is not verified traceability.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / BLOCKED / PROVISIONAL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
Tests added:
Tests modified:
Tests removed/skipped:
Weakening concerns:
Atomic behavior/assertion traceability:
residual escape hypothesis:
Required fixes:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
