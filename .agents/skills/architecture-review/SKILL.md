---
name: architecture-review
description: Review a diff for architecture drift, wrong abstractions, boundary violations, coupling, and chunk-scope violations.
---

# Architecture Review

Review current changes against the initiative plan and architecture boundaries.

## Shared evidence

Use `reviewer-evidence-protocol` first. Bind the review to its exact target,
inspect relevant unchanged owners and consumers, replay prior findings, separate
executed from inspected evidence, state uncertainty and freshness, and hand off
non-architecture findings without inventing another specialty's verdict.
Use canonical reviewer IDs from the initiative `REVIEWER_MATRIX.md` in handoffs.

## Focus

- Did the change stay inside the approved chunk?
- Did it introduce the wrong abstraction?
- Did it mix orchestration with execution?
- Did it mix policy with persistence?
- Did it bypass an existing boundary?
- Did it create hidden coupling?
- Did it introduce speculative generality?
- Did it add complexity without necessity?
- Did it make future chunks harder?
- Is the data/control flow understandable?

## Special rule

Architecture drift is blocking even when tests pass.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / FAIL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
Boundary violations:
Abstraction risks:
Coupling risks:
Simpler alternative:
Required fixes:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
