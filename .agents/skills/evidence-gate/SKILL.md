---
name: evidence-gate
description: "Check deterministic proof before expensive reviewer fanout: tests, lint, typecheck, scope, CI integrity, test delta, dependencies, and PR size."
---

# Evidence Gate

Run deterministic proof checks before reviewer fanout.

The lead runs shared checks once per clean candidate and supplies the exact
target, command, exit status, producer, and artifact location. Reviewers inspect
that evidence and run only discriminating probes their specialty still needs.
Keep full backend/coverage runs in hosted CI; do not duplicate them locally.
Unavailable hosted evidence remains pending, never an inferred pass.

## Check

- Changed files are inside the stated scope.
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
- Reviewer proof-quality inputs name the claimed boundary, proof strength,
  custody, compatibility, discriminating probe, and remaining uncertainty.
- A passing summary does not claim private session-receipt custody. It records
  the complete proof-quality dimensions below without copying a private receipt.

## Output

```text
Evidence gate: PASS / FAIL / BLOCKED
Commands run:
Results:
Scope exceptions:
CI/test integrity concerns:
Required fixes before review:
Proof-quality summary:
- exact reviewed head:
- claimed boundaries and compatible proof:
- proof strength:
- execution custody:
- discriminating probe result:
- unavailable proof or uncertainty:
```

Do not run expensive reviewer fanout until this passes or blockers are explicitly documented.
