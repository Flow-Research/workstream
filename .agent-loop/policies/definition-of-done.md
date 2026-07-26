# Definition Of Done

A Workstream engineering chunk is done only when all applicable sections pass.

## Scope

- The change has a stated goal and reviewable scope. Large or risky changes use
  a plan or chunk contract; small changes may document this in the PR.
- Changed files stay inside the stated scope, or exceptions are explained.
- No unrelated refactor, product behavior, schema, dependency, or CI weakening is included.

## Evidence

- Verification commands ran or blockers are documented.
- Stale wording scan ran.
- Markdown link check ran for changed docs.
- Material internal review findings are summarized when internal review applies.
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

- Applicable risk-based internal reviewers completed.
- External review findings from CodeRabbit, GitHub review, or CI are reviewed.
- Critical and High internal or external findings are fixed or explicitly waived
  by the human owner.
- Medium findings have a human decision or documented follow-up.
- No sub-agent sessions remain open.

## Human Checkpoint

- The user explicitly approves merge for the specific PR.
- Codex stops after the chunk and does not start the next chunk automatically.
