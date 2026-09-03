---
name: plan-to-chunks
description: Convert an approved multi-PR overview into PR-sized Commitrail change records with scope, acceptance criteria, evidence, reviewers, and human focus.
---

# Plan to Chunks

Use after a Commitrail initiative overview is approved and before implementation.

## Process

1. Read the initiative `OVERVIEW.md` and current authoritative sources.
2. Identify dependency order.
3. Split work into 1-N reviewable PR-sized chunks.
4. Keep each chunk bounded and independently reviewable.
5. When a boundary starts, create one record from
   `.commitrail/CHANGE_TEMPLATE.md` in that initiative directory. Do not create
   every future record in advance.

## Each chunk must include

- Change ID and parent initiative
- Durable disposition and intended merge outcome
- Goal
- Why this chunk exists
- Risk class
- Allowed files
- Not allowed changes
- Acceptance criteria
- Verification commands
- Required reviewers
- Human review focus
- Evidence and remaining uncertainty

## Rules

- Do not create giant chunks.
- Do not mix unrelated concerns.
- Do not bury architecture changes in implementation chunks.
- Keep future boundaries in the overview; create their record only when the
  human starts that boundary.
