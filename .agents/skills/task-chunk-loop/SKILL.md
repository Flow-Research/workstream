---
name: task-chunk-loop
description: Execute one bounded change with proportionate planning, evidence, review, and a PR trust bundle.
---

# Task Chunk Loop

Execute one bounded change. A chunk contract is recommended for broad or risky
work and optional for small changes.

## Inputs

- Chunk contract or PR-stated intent and scope.
- Initiative artifacts when they exist.
- Current repository instructions, specifications, ADRs, and architecture boundaries.

## Required process

1. Read the applicable contract or restate the requested intent and scope.
2. Restate:
   - goal
   - why this chunk exists
   - allowed files
   - not allowed changes
   - acceptance criteria
   - risk class
   - required reviewers
   - human review focus
3. Produce a short implementation plan.
4. Run plan review for L0/L1 or architecture/security-sensitive work.
5. Implement only the bounded change.
6. Run relevant tests/checks.
7. Run deterministic proof checks before reviewer fanout.
8. If deterministic checks fail, fix cheap blockers before reviewer fanout.
9. Run required reviewer agents or skills based on risk routing.
10. Fix all Critical and High findings.
11. Re-run failed reviewers.
12. Before a passing readiness claim, summarize each required reviewer's exact
    head, verdict, compatible proof boundary, proof strength, execution custody,
    discriminating probe, and uncertainty without copying private session
    receipts into Git.
13. Summarize material reviewer findings in the same Commitrail change record
    or PR; add another record only when independently useful.
14. Stop after two failed repair cycles on the same class of issue.
15. Complete the change record and PR trust summary without duplicating them.
16. Stop for human review.

## Hard stops

Stop immediately if:

- required scope exceeds the stated boundary
- architecture direction changes
- auth/payment/policy/data boundary changes beyond contract
- tests or CI must be weakened to pass
- secrets or production credentials are required
- same blocker remains after two repair attempts

## Output

Return:

1. Summary
2. Files changed
3. Tests/checks run
4. Evidence gate result
5. Reviewer results
6. Remaining risks
7. PR trust bundle draft
8. Explicit stop: "Chunk complete or blocked. Awaiting human review."
