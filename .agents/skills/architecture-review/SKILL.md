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
Atomize every material criterion. For every behavior atom, record its owner, implementation source, named proof,
execution custody, and result. Missing or narrative-only rows block PASS.

## Candidate proof-quality obligations

Use the shared proof-strength vocabulary and schema-owned compatibility rules;
do not invent a parallel proof taxonomy. Select relevant stable failure-pattern
IDs and explain why they apply. Require a discriminating test-of-the-test probe
for every final PASS or PASS WITH LOW RISKS. Never infer proof strength or execution custody from
filenames, test names, command labels, or narrative claims. Incompatible or
unavailable proof blocks PASS for the claimed behavior.

Probe composite ownership, schema/model/database parity, syntax-aware private
edges, and composition-root wiring. Require database custody only when the
claim crosses that boundary. These obligations remain candidates until blind
evaluation in `WS-CI-005-03`.

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
Result: PASS / PASS WITH LOW RISKS / FAIL
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
