---
name: risk-router
description: Classify work by blast radius, risk, SLA, model budget, reviewers, and human gates before implementation.
---

# Risk Router

Use before implementation and before reviewer fanout.

## Classify

- Risk uses one closed scale (lower number means higher risk):
  - L0: cross-system authority, irreversible data change, or broad critical impact.
  - L1: bounded authorization, security, schema, policy, CI, or architecture change.
  - L2: routine low-risk maintenance, documentation, or behavior-preserving repair.
- Urgency: only an actual user or operational constraint; do not invent an SLA.
- Work type: architecture, infra, bug, test, docs, CI, dependency, maintenance, read-only
- Required reviewers
- Human checkpoint requirement
- Token budget posture

Route only affected specialties using `.ci/reviewer-evidence/REVIEWER_MATRIX.md`.
Risk depends on semantics, not file extension: a planning document can be L1.
Use Sol high with minimal bounded context; Astra remains the lead. Do not
escalate models automatically or spawn all reviewers merely because they exist.

## Escalators

Escalate if the work touches:

```text
auth permissions payment payout billing policy audit ledger migration schema secrets CI deploy workflow data ownership PII tenant boundary LLM prompt input tools
```

## Output

```text
Risk class:
Urgency (if supplied):
Work type:
Required reviewers:
Human gate:
Budget posture:
Why:
```
