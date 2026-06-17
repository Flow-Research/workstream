---
name: security-review
description: Review a diff for security, auth, permission, payment, data, secrets, prompt injection, and audit risks.
---

# Security Review

Review current changes against security boundaries.

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
