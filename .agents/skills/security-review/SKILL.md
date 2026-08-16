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

End with PASS / PASS WITH LOW RISKS / FAIL.

Protocol envelope: target / run / evidence / findings / uncertainty / freshness.
A Medium finding requires explicit human disposition. Keep Low/Informational
findings visible.
