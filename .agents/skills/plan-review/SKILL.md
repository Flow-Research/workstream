---
name: plan-review
description: Review an implementation plan before code is written, especially for L1 infrastructure, architecture, auth, payment, or policy work.
---

# Plan Review

Review the plan before implementation.

## Focus

- Is the plan aligned with intent?
- Is the chunk small enough?
- Are allowed files correct?
- Are not-allowed changes clear?
- Are architecture boundaries preserved?
- Are security/payment/auth/data risks addressed?
- Are acceptance criteria testable?
- Is the verification strategy enough?
- Can each proposed fixture reach the assertion under existing guards? Trace a
  concrete counterexample and valid control through the actual sequence. A test
  name or plausible matrix row alone does not prove feasibility.
- Are verification commands real, or explicitly named future implementation
  tests? Are owner boundaries and dependencies unambiguous and acyclic?
- Does the evidence distinguish inspected contract feasibility from future
  runtime execution?

## Output

- PASS
- PASS WITH LOW RISKS
- BLOCKED
- PROVISIONAL (required evidence unavailable)

Include concrete required changes if not PASS.
