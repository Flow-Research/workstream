---
name: product-ops-review
description: Review Workstream changes for project manager, contributor, reviewer, operator, payment, revision, and audit workflow correctness.
---

# Product/Ops Review

Review the change from the perspective of people operating Workstream.

## Shared evidence

Use `reviewer-evidence-protocol` first. Bind the review to its exact target,
inspect relevant unchanged lifecycle and operator contracts, replay prior
findings, separate executed from inspected evidence, state uncertainty and
freshness, and hand off engineering-only findings without inventing another
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

Apply shared proof fields proportionately; do not require database ceremony for
product-only claims or convert engineering evidence into product truth. Use
product lifecycle evidence without inventing an engineering specialty verdict.
These obligations remain candidates until blind evaluation in `WS-CI-005-03`.

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
Result: PASS / PASS WITH LOW RISKS / FAIL
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
