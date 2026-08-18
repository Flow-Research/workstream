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
Atomize every material criterion. For every behavior atom, record its owner, implementation source, named proof,
execution custody, and result. Missing or narrative-only rows block PASS.

## Adopted proof-quality obligations

Use the shared proof-strength vocabulary and schema-owned compatibility rules;
do not invent a parallel proof taxonomy. Select relevant stable failure-pattern
IDs and explain why they apply. Require a discriminating test-of-the-test probe
for every final PASS or PASS WITH LOW RISKS. Never infer proof strength or execution custody from
filenames, test names, command labels, or narrative claims. Incompatible or
unavailable proof blocks PASS for the claimed behavior.

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
Result: PASS / PASS WITH LOW RISKS / FAIL
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
