---
name: circuit-breaker
description: Fast-fail or split unreviewable agent work based on scope, size, file types, boundary count, missing evidence, or unclear intent.
---

# Circuit Breaker

Use before deep review.

## Stop or split if

- Diff is too large for the risk class.
- More than one major boundary is touched without approval.
- PR lacks intent, acceptance criteria, or evidence.
- CI/workflows changed unexpectedly.
- Tests are heavily rewritten without explanation.
- Schema/migration changes appear without approval.
- Auth/payment/policy/data touched without required reviewers.
- Agent cannot explain the change in one sentence.

## Default size guidelines

- L1 infrastructure: prefer under 500 changed lines.
- L2 bug/refactor: prefer under 300 changed lines.
- Maintenance/docs: flexible, but still reviewable; classify semantic risk using
  `risk-router`, not a separate risk scale.

These are guidelines, not laws. Explain exceptions.

An authorized cross-file repair may be one cohesive change. Diagnose missing
scope/evidence and repair the current record rather than creating ceremonial
PRs. Stop for a human only when authority or a material decision is missing.

## Output

```text
Circuit breaker: PASS / SPLIT REQUIRED / STOP
Reasons:
Required action:
```
