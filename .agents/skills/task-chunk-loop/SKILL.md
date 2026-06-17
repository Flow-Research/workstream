---
name: task-chunk-loop
description: Execute exactly one approved chunk using bounded implementation, evidence gates, zero-trust reviewers, repair loop, and PR trust bundle. Do not start the next chunk.
---

# Task Chunk Loop

Execute exactly one approved chunk.

## Inputs

- Chunk contract path.
- Initiative artifacts: `INTENT.md`, `DISCOVERY.md`, `PLAN.md`, `CHUNK_MAP.md`.
- Policies under `.agent-loop/policies/`.

## Required process

1. Read the chunk contract and parent initiative artifacts.
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
5. Implement only the approved chunk.
6. Run relevant tests/checks.
7. Run deterministic proof checks before reviewer fanout.
8. If deterministic checks fail, fix cheap blockers before reviewer fanout.
9. Run required reviewer agents or skills based on risk routing.
10. Fix all Critical and High findings.
11. Re-run failed reviewers.
12. Write internal review evidence.
13. Run the internal review evidence gate.
14. Stop after two failed repair cycles on the same class of issue.
15. Produce a PR trust bundle.
16. Stop for human review.

## Hard stops

Stop immediately if:

- required scope exceeds the chunk contract
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
