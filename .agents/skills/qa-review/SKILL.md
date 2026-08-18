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
Atomize every material criterion. For every behavior atom, record its owner, implementation source, named proof,
execution custody, and result. Missing or narrative-only rows block PASS.

## Candidate proof-quality obligations

Use the shared proof-strength vocabulary and schema-owned compatibility rules;
do not invent a parallel proof taxonomy. Select relevant stable failure-pattern
IDs and explain why they apply. Require a discriminating test-of-the-test probe
for every final PASS or PASS WITH LOW RISKS. Never infer proof strength or execution custody from
filenames, test names, command labels, or narrative claims. Incompatible or
unavailable proof blocks PASS for the claimed behavior.

Simulate the pre-fix defect and require the named test to fail for the exact
behavior atom. Reject fixtures that abort before the intended assertion or
inputs the pre-fix code already rejects. These obligations remain candidates
until blind evaluation in `WS-CI-005-03`.

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
- Split compound criteria into behavior atoms. For each atom name the owner,
  implementation source, exact test, execution custody, and observed result.
- A test module name, broad command, or prose promise is not proof of every atom.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / FAIL
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
