---
name: security-review
description: Review a diff for security, auth, permission, payment, data, secrets, prompt injection, and audit risks.
---

# Security Review

Review current changes against security boundaries.

## Shared evidence

Use `reviewer-evidence-protocol` first. Bind the review to its exact target,
inspect relevant unchanged trust boundaries and consumers, replay prior
findings, separate executed from inspected evidence, state uncertainty and
freshness, and hand off non-security findings without inventing another
specialty's verdict.
Use canonical reviewer IDs from the initiative `REVIEWER_MATRIX.md` in handoffs.
Atomize every material criterion. For every behavior atom, record its owner, implementation source, named proof,
execution custody, and result. Missing or narrative-only rows block PASS.

## Focus

- Authentication
- Authorization
- Permissions/roles
- Payment or payout boundaries
- Tenant/user data ownership
- PII exposure
- Secrets handling
- Input validation
- Injection risks
- Prompt injection / LLM tool boundaries
- Unsafe logging/errors
- Dependency risk
- Auditability

## Rules

- Be adversarial.
- Do not approve because tests pass.
- Findings must be concrete.
- Critical/High findings block PR.

## Completeness probe

Decompose each protected behavior across actor/context, action, project or
resource, lifecycle state, failure mode, and forbidden evidence/side effect.
Trace both allow and deny paths, including cross-tenant/resource substitution,
replay, revocation, and transaction failure. Missing negative-path proof blocks
a passing verdict.

## Output

For each finding:

```text
Severity:
Location:
Problem:
Why it matters:
Suggested fix:
Blocks PR: yes/no
```

Include atomic traceability and the residual escape hypothesis for authorization.

End with PASS / PASS WITH LOW RISKS / FAIL.

Protocol envelope: target / run / evidence / findings / uncertainty / freshness.
A Medium finding requires explicit human disposition. Keep Low/Informational
findings visible.
