---
name: plan-to-chunks
description: Convert an approved plan into PR-sized chunk contracts with scope, acceptance criteria, reviewer requirements, and human review focus.
---

# Plan to Chunks

Use after `PLAN.md` exists and before implementation.

## Process

1. Read `INTENT.md`, `DISCOVERY.md`, and `PLAN.md`.
2. Identify dependency order.
3. Split work into 1-N reviewable PR-sized chunks.
4. Keep each chunk bounded and independently reviewable.
5. For each chunk, start from `.agent-loop/templates/CHUNK_CONTRACT.md` and
   write the contract under `chunks/`.

## Each chunk must include

- A canonical first line in the exact template form
  `# Chunk Contract: <CHUNK_ID> — <TITLE>`. The internal evidence gate reads
  the complete lifecycle ID from this heading and fails closed when the heading
  is missing or malformed.
- Parent initiative
- Goal
- Why this chunk exists
- Risk class
- SLA
- Allowed files
- Not allowed changes
- Acceptance criteria
- Verification commands
- Required reviewers
- Human review focus
- Stop conditions

## Rules

- Do not create giant chunks.
- Do not mix unrelated concerns.
- Do not bury architecture changes in implementation chunks.
- Mark future work explicitly instead of doing it early.
