---
name: product-ops-review
description: Review Workstream changes for project manager, worker, reviewer, operator, payment, revision, and audit workflow correctness.
---

# Product/Ops Review

Review the change from the perspective of people operating Workstream.

## Focus

- project manager setup flow
- worker task claiming and submission flow
- reviewer packet and finding flow
- revision loop clarity
- checker results and operator actions
- payment and reputation records
- auditability and evidence availability
- wording consistency with `README.md`, `docs/glossary.md`, and `docs/architecture_lockdown.md`
- confusing names, vague statuses, or role ambiguity

## Rules

- Treat naming drift as a real product risk.
- Do not approve a flow that requires chat memory or Slack memory to understand.
- Do not collapse worker-facing decisions with internal checker states.
- Confirm user-facing review decisions remain `accept`, `needs_revision`, and `reject`.
- Confirm out-of-band guidance becomes a guide, policy, template, checker, or ADR before it is enforceable.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / FAIL
Operator workflow risks:
Worker/reviewer workflow risks:
Payment/reputation risks:
Naming or wording drift:
Required fixes:
```
