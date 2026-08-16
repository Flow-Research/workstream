---
name: reuse-dedup-review
description: Review a diff for duplicated helpers, missed existing abstractions, redundant logic, and code reuse blindness.
---

# Reuse / Dedup Review

Agents often create new helpers instead of reusing existing code. Check for that.

## Shared evidence

Use `reviewer-evidence-protocol` first. Bind the review to its exact target,
inspect relevant unchanged helpers and public abstractions, replay prior
findings, separate executed from inspected evidence, state uncertainty and
freshness, and hand off non-reuse findings without inventing another
specialty's verdict.
Use canonical reviewer IDs from the initiative `REVIEWER_MATRIX.md` in handoffs.

## Focus

- New helper duplicates existing helper.
- New validation logic duplicates old validation logic.
- New policy path bypasses existing policy path.
- Naming convention forks.
- Similar abstractions now exist in multiple places.
- Shared behavior belongs in existing module.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / FAIL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
Possible duplicates:
Existing code to reuse:
Required fixes:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
