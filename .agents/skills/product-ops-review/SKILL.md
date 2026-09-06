---
name: product-ops-review
description: Review Workstream changes for project manager, contributor, reviewer, operator, payment, revision, and audit workflow correctness.
---

# Product/Ops Review

Review the change from the perspective of people operating Workstream.

## Shared evidence

Read `reviewer-evidence-protocol` first; it owns the exact target, prior findings,
executed from inspected evidence, uncertainty, freshness, traceability, and
verdict mechanics. Use canonical IDs from
`.ci/reviewer-evidence/REVIEWER_MATRIX.md` to hand off other specialties.
Apply this skill only to the assigned impact cone.

Apply shared proof fields proportionately; do not require database ceremony for
product-only claims or convert engineering evidence into product truth. Use
product lifecycle evidence without inventing an engineering specialty verdict.
These obligations are adopted through the blind evaluation recorded by
`WS-CI-005-03`.

## Focus

- project manager setup flow
- contributor task claiming and submission flow
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
- Do not collapse contributor-facing decisions with internal checker states.
- Confirm user-facing review decisions remain `accept`, `needs_revision`, and `reject`.
- Confirm out-of-band guidance becomes a guide, policy, template, checker, or ADR before it is enforceable.

## Completeness probe

Trace every lifecycle atom through actor, prerequisite, state transition,
failure/retry/revision path, evidence produced, and downstream consumer. Include
separation-of-duty and cross-project variants. Missing operator recovery or
user-visible failure behavior blocks a passing verdict.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / BLOCKED / PROVISIONAL
Protocol envelope: target / run / evidence / findings / uncertainty / freshness
Operator workflow risks:
Contributor/reviewer workflow risks:
Payment/reputation risks:
Naming or wording drift:
Lifecycle traceability and residual escape:
Required fixes:
```

Critical/High findings block. A Medium finding requires explicit human
disposition. Keep Low/Informational findings visible. Engineering verdicts must
never become product decisions (`accept`, `needs_revision`, or `reject`).
