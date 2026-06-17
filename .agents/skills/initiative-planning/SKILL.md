---
name: initiative-planning
description: Plan a large or ambiguous engineering initiative before implementation. Produces intent, discovery, plan, chunk map, and chunk contracts. Use before writing code for non-trivial work.
---

# Initiative Planning

Use this skill when the user describes a large, ambiguous, architectural, or multi-PR task.

## Mode

Start read-only. Do not edit application code.

## Inputs

- Initiative folder path, or create one under `.agent-loop/initiatives/`.
- Human goal and constraints.
- Project policies under `.agent-loop/policies/`.

## Required output artifacts

Create or update:

```text
INTENT.md
DISCOVERY.md
PLAN.md
CHUNK_MAP.md
STATUS.md
RISKS.md
DECISIONS.md
chunks/<ID>-01.md ... chunks/<ID>-N.md
```

## Process

1. Restate the human goal.
2. Identify what is known, unknown, and risky.
3. Explore the repo read-only.
4. Write `DISCOVERY.md` with concrete files, modules, tests, and risks.
5. Write `INTENT.md` with the why, success state, non-goals, and human decisions needed.
6. Write `PLAN.md` with proposed approach, alternatives rejected, boundaries preserved, and verification strategy.
7. Split the plan into reviewable PR-sized chunks in `CHUNK_MAP.md`.
8. Create one chunk contract per chunk.
9. Mark the first chunk as proposed, not active, until human approval.
10. Stop. Do not implement.

## Chunking rules

- Each chunk should map to one PR.
- Each chunk must have allowed files, not-allowed changes, acceptance criteria, risk class, reviewer set, and human review focus.
- L1 chunks must be small enough for careful human review.
- If a chunk is too large, split it.

## Output format

End with:

1. Initiative summary
2. Proposed chunk list
3. Main risks
4. Human decisions needed
5. Recommended first chunk
6. Explicit stop: "Planning complete. Awaiting human approval before implementation."
