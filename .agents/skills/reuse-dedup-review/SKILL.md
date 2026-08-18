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
Atomize every material criterion. For every behavior atom, record its owner, implementation source, named proof,
execution custody, and result. Missing or narrative-only rows block PASS.

## Candidate proof-quality obligations

Use the shared proof-strength vocabulary and schema-owned compatibility rules;
do not invent a parallel proof taxonomy. Select relevant stable failure-pattern
IDs and explain why they apply. Require a discriminating test-of-the-test probe
for every final PASS or PASS WITH LOW RISKS. Never infer proof strength or execution custody from
filenames, test names, command labels, or narrative claims. Incompatible or
unavailable proof blocks PASS for the claimed behavior.

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
Result: PASS / PASS WITH LOW RISKS / FAIL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
Possible duplicates:
Existing code to reuse:
Responsibility traceability and residual escape:
Required fixes:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
