---
name: architecture-review
description: Review a diff for architecture drift, wrong abstractions, boundary violations, coupling, and chunk-scope violations.
---

# Architecture Review

Review current changes against the initiative plan and architecture boundaries.

## Shared evidence

Read `reviewer-evidence-protocol` first; it owns the exact target, prior findings,
executed from inspected evidence, uncertainty, freshness, traceability, and
verdict mechanics. Use canonical IDs from
`.ci/reviewer-evidence/REVIEWER_MATRIX.md` to hand off other specialties.
Apply this skill only to the assigned impact cone.

Probe composite ownership, schema/model/database parity, syntax-aware private
edges, and composition-root wiring. Require database custody only when the
claim crosses that boundary. These obligations are adopted through the blind
evaluation recorded by `WS-CI-005-03`.

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

## Completeness probe

Build an owner/consumer/public-port matrix for every changed boundary. Trace
construction, runtime composition, persistence ownership, and every known
consumer. Search for private imports and parallel paths. Treat an uninspected
consumer or unmapped ownership transition as missing proof.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / BLOCKED / PROVISIONAL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
Boundary violations:
Abstraction risks:
Coupling risks:
Atomic traceability and residual escape:
Simpler alternative:
Required fixes:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible.
