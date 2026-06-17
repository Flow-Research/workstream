# Definition Of Done

A Workstream engineering chunk is done only when all applicable sections pass.

## Scope

- The chunk maps to one approved contract.
- Changed files stay inside the allowed file set, or exceptions are documented.
- No unrelated refactor, product behavior, schema, dependency, or CI weakening is included.

## Evidence

- Verification commands ran or blockers are documented.
- Stale wording scan ran.
- Markdown link check ran for changed docs.
- Internal review evidence exists and includes required tracks.
- PR trust bundle summarizes intent, scope, proof, and remaining risk.

## Security

- Auth, permission, payment, policy, audit, and data boundaries are preserved.
- Secrets are not printed, committed, transformed, or required for local proof.
- Errors and logs do not expose sensitive data.

## Architecture

- Router, service, repository, adapter, schema, and policy responsibilities remain separated.
- No speculative abstraction is introduced.
- Naming is precise enough for future operators and engineers.

## Review

- Required internal reviewer agents completed.
- External review findings from CodeRabbit, GitHub review, or CI are reviewed.
- Critical and High internal or external findings are fixed or explicitly waived
  by the human owner.
- Medium findings have a human decision or documented follow-up.
- No sub-agent sessions remain open.

## Human Checkpoint

- The user explicitly approves merge for the specific PR.
- Codex stops after the chunk and does not start the next chunk automatically.
