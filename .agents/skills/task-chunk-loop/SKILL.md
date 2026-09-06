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
9. Freeze a clean review candidate. Supply impact-routed reviewers its base/head,
   current change record, bounded file list, prior finding IDs, and shared check
   evidence. Use an isolated clean checkout if unrelated work must be preserved.
   Do not forward the full conversation or bulk-read archives by default.
10. Collect the review wave before batching valid repairs. Do not change the
    target underneath running reviewers. Fix Critical/High findings; resolve or
    explicitly disposition every other valid finding.
11. Re-run affected reviewers, including previously passing tracks when their
    evidence was invalidated. Supply the delta and prior findings. Never relabel
    an old review with the new SHA.
12. Before a passing readiness claim, summarize each required reviewer's exact
    head, verdict, compatible proof boundary, proof strength, execution custody,
    discriminating probe, and uncertainty without copying private session
    receipts into Git.
13. Summarize material reviewer findings in the same Commitrail change record
    or PR; add another record only when independently useful.
14. Repeated failure requires root-cause diagnosis and a narrower reproducer,
    not another speculative patch or an arbitrary stop. Recover failed reviewer
    sessions with a bounded replacement; unavailable evidence is not a pass.
15. Keep durable intent/decisions in the change record and current head, checks,
    reviewer freshness, and external conversations in the PR trust summary.
16. Continue authorized repairs and hosted-check monitoring until complete or
    genuinely blocked. Keep the human informed. Wait for required reviewers and
    checks before reporting completion; leave merge to the authorized human.

## Hard stops

Stop immediately if:

- required scope exceeds the stated boundary
- architecture direction changes
- auth/payment/policy/data boundary changes beyond contract
- tests or CI must be weakened to pass
- secrets or production credentials are required

A failed command, reviewer crash, or repair count does not create a new
permission requirement. Stop only when safe progress requires missing authority,
a material human decision, or an unavailable prerequisite. Do not start the next
product change automatically after completing this one.

## Output

Return:

1. Summary
2. Files changed
3. Tests/checks run
4. Evidence gate result
5. Reviewer results
6. Remaining risks
7. PR trust bundle draft
8. Actual disposition and the precise remaining human action or blocker.
