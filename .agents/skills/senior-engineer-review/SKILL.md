---
name: senior-engineer-review
description: Review a diff like a senior engineer for maintainability, simplicity, readability, operational risk, and long-term ownership.
---

# Senior Engineer Review

Review for engineering judgment.

## Shared evidence

Use `reviewer-evidence-protocol` first. Bind the review to its exact target,
inspect relevant unchanged ownership and operational context, replay prior
findings, separate executed from inspected evidence, state uncertainty and
freshness, and hand off specialty findings without inventing their verdicts.
Use canonical reviewer IDs from the initiative `REVIEWER_MATRIX.md` in handoffs.

## Focus

- Simplicity
- Readability
- Naming
- Error handling
- Operational risk
- Maintainability
- Over-engineering
- Duplicated logic
- Ownership in 3-6 months
- Fit with existing conventions

## Completeness probe

Trace each responsibility to one owner, one failure boundary, one operational
signal, and one maintenance path. Inspect size, branching, transaction/error
handling, and rollback independently. State the most plausible maintenance or
operational defect still hidden by otherwise green proof.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / FAIL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
Maintainability risks:
Simplicity improvements:
Operational concerns:
Responsibility traceability and residual escape:
Required fixes:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
