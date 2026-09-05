---
name: reuse-dedup-review
description: Review a diff for duplicated helpers, missed existing abstractions, redundant logic, and code reuse blindness.
---

# Reuse / Dedup Review

Agents often create new helpers instead of reusing existing code. Check for that.

## Shared evidence

Read `reviewer-evidence-protocol` first; it owns the exact target, prior findings,
executed from inspected evidence, uncertainty, freshness, traceability, and
verdict mechanics. Use canonical IDs from
`.ci/reviewer-evidence/REVIEWER_MATRIX.md` to hand off other specialties.
Apply this skill only to the assigned impact cone.

Compare canonical rule representations across schema, service, public API,
migration, and database constraint. Prove whether one owner can be reused before
accepting another representation. These obligations are adopted through the
blind evaluation recorded by `WS-CI-005-03`.

## Focus

- New helper duplicates existing helper.
- New validation logic duplicates old validation logic.
- New policy path bypasses existing policy path.
- Naming convention forks.
- Similar abstractions now exist in multiple places.
- Shared behavior belongs in existing module.

## Completeness probe

For each new helper, schema, policy path, or abstraction, search by behavior,
types, call sites, and ownership—not name alone. Map the new responsibility to
the closest existing public owner and explain why reuse or extension is or is
not valid. Unsearched likely owners are missing proof.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / BLOCKED / PROVISIONAL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
Possible duplicates:
Existing code to reuse:
Responsibility traceability and residual escape:
Required fixes:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
