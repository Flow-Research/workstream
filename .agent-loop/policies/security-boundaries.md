# Security Boundaries

## Always Sensitive

```text
credentials
secrets
tokens
sessions
authentication
authorization
permissions
payments
PII
tenant/user data
submission artifacts
review evidence
checker results
audit ledgers
LLM prompts and tool inputs
```

## Workstream-Specific Rules

- Workstream verifies external Flow authentication; it does not own passwords or primary sessions.
- Dev auth must fail closed outside explicit local/test environments.
- Payment records are separate from acceptance decisions.
- Submitted artifacts and checker results are audit evidence and must not be mutated silently.
- User-controlled text is untrusted when it reaches LLM prompts, shell commands,
  SQL, filesystem paths, URLs, or rendered HTML.

## Security Review Questions

- Can a lower-privileged actor perform a higher-privileged action?
- Can a worker, reviewer, or project manager access another actor's private data?
- Can a stale guide or policy context be used silently?
- Can secrets or tokens leak through logs, errors, artifacts, or review bundles?
- Can test/demo auth become production auth by misconfiguration?
