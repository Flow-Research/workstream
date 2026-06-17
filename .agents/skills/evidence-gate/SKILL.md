---
name: evidence-gate
description: Check deterministic proof before expensive reviewer fanout: tests, lint, typecheck, scope, CI integrity, test delta, dependencies, and PR size.
---

# Evidence Gate

Run deterministic proof checks before reviewer fanout. Run internal review
evidence validation after reviewer fanout has completed and the evidence file
exists.

## Check

- Changed files are inside chunk scope.
- PR size is reviewable.
- Relevant tests ran.
- Lint ran if applicable.
- Typecheck ran if applicable.
- Build ran if applicable.
- CI config was not weakened.
- Package scripts were not weakened.
- Coverage thresholds were not lowered.
- Tests were not skipped/deleted/weakened without explanation.
- New dependencies were approved.

## Output

```text
Evidence gate: PASS / FAIL / BLOCKED
Commands run:
Results:
Scope exceptions:
CI/test integrity concerns:
Required fixes before review:
```

Do not run expensive reviewer fanout until this passes or blockers are explicitly documented.
