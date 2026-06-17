# Merge Policy

## Non-Negotiables

- Codex must not merge a PR unless the user explicitly approves that specific PR.
- External review passing does not replace internal reviewer agents.
- CI passing does not replace human review.
- L0 and L1 changes require human checkpoint before moving to the next chunk.
- If a PR changes CI, auth, permission, policy, payment, migration, or lifecycle
  behavior, the PR trust bundle must call that out directly.

## Human Merge Checklist

Before merge, the human reviewer should be able to say:

- I verified that the user explicitly approved this specific PR for merge.
- I understand the intent.
- I understand the chunk boundary.
- I reviewed the evidence.
- I reviewed changed tests before trusting green checks.
- I checked CI/workflow changes.
- I reviewed internal and external reviewer findings.
- I can explain what changed and why.
- I accept the remaining risks.
