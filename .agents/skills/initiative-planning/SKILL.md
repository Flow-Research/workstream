---
name: initiative-planning
description: Plan large, ambiguous, or multi-PR work before implementation using one concise Commitrail initiative overview and PR-sized change records.
---

# Initiative Planning

Use this skill when the user describes a large, ambiguous, architectural, or multi-PR task.

## Mode

Start read-only. Do not edit application code.

## Inputs

- Human goal and constraints.
- Current code, tests, ADRs, specifications, `.commitrail/INDEX.md`, and open PRs.

## Record

Create one `.commitrail/initiatives/<ID>/OVERVIEW.md`. Keep intent, relevant
discovery, design, dependencies, risks, durable disposition, and proposed
PR-sized boundaries in that file. Do not create separate intent, discovery,
plan, status, risk, decision, and chunk-map files by default.

## Process

1. Restate the human goal.
2. Identify what is known, unknown, and risky.
3. Explore the repo read-only.
4. Write one concise overview with concrete observations, intent, non-goals,
   chosen design, rejected alternatives, risks, verification strategy, and
   proposed PR boundaries.
5. Add or update its one row in `.commitrail/INDEX.md`.
6. Mark its durable disposition `Planned` and stop for human approval.

## Chunking rules

- Each boundary maps to one PR and one record based on
  `.commitrail/CHANGE_TEMPLATE.md` when implementation starts.
- Each record states allowed files, prohibited changes, acceptance criteria,
  risk, impact-routed reviewers, evidence, and human review focus.
- L1 chunks must be small enough for careful human review.
- If a chunk is too large, split it.

## Output format

End with:

1. Initiative summary
2. Proposed PR-sized boundary list
3. Main risks
4. Human decisions needed
5. Recommended first bounded change
6. Explicit stop: "Planning complete. Awaiting human approval before implementation."
