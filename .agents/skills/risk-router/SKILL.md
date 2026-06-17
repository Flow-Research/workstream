---
name: risk-router
description: Classify work by blast radius, risk, SLA, model budget, reviewers, and human gates before implementation.
---

# Risk Router

Use before implementation and before reviewer fanout.

## Classify

- Risk: L0/L1/L2/L3/L4
- SLA: P0/P1/P2/P3
- Work type: architecture, infra, bug, test, docs, CI, dependency, maintenance, read-only
- Required reviewers
- Human checkpoint requirement
- Token budget posture

## Escalators

Escalate if the work touches:

```text
auth permissions payment payout billing policy audit ledger migration schema secrets CI deploy workflow data ownership PII tenant boundary LLM prompt input tools
```

## Output

```text
Risk class:
SLA:
Work type:
Required reviewers:
Human gate:
Budget posture:
Why:
```
