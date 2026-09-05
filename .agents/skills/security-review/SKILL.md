---
name: security-review
description: Review a diff for security, auth, permission, payment, data, secrets, prompt injection, and audit risks.
---

# Security Review

Review current changes against security boundaries.

## Shared evidence

Read `reviewer-evidence-protocol` first; it owns the exact target, prior findings,
executed from inspected evidence, uncertainty, freshness, traceability, and
verdict mechanics. Use canonical IDs from
`.ci/reviewer-evidence/REVIEWER_MATRIX.md` to hand off other specialties.
Apply this skill only to the assigned impact cone.

Probe actor, tenant, and resource substitution; nullable or fail-open state;
replay; concealment; and composite ownership. Require repository-isolation
evidence for stored ownership, direct-SQL evidence for ORM-bypassed database
enforcement, and schema-compatible service or composition evidence for
application authorization.
These obligations are adopted through the blind evaluation recorded by
`WS-CI-005-03`.

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

End with PASS / PASS WITH LOW RISKS / BLOCKED / PROVISIONAL.

Protocol envelope: target / run / evidence / findings / uncertainty / freshness.
A Medium finding requires explicit human disposition. Keep Low/Informational
findings visible.
