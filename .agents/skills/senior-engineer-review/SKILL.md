---
name: senior-engineer-review
description: Review a diff like a senior engineer for maintainability, simplicity, readability, operational risk, and long-term ownership.
---

# Senior Engineer Review

Review for engineering judgment.

## Shared evidence

Read `reviewer-evidence-protocol` first; it owns the exact target, prior findings,
executed from inspected evidence, uncertainty, freshness, traceability, and
verdict mechanics. Use canonical IDs from
`.ci/reviewer-evidence/REVIEWER_MATRIX.md` to hand off other specialties.
Apply this skill only to the assigned impact cone.

Probe permissive fakes and misleading abstractions, and weigh proof cost against
escape risk. Do not substitute cheap proof for custody required by the claimed
boundary. These obligations are adopted through the blind evaluation recorded
by `WS-CI-005-03`.

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
Result: PASS / PASS WITH LOW RISKS / BLOCKED / PROVISIONAL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
Maintainability risks:
Simplicity improvements:
Operational concerns:
Responsibility traceability and residual escape:
Required fixes:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
