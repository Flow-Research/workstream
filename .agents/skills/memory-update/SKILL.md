---
name: memory-update
description: Update durable repo memory after planning, merge, rejection, blocker, or repeated agent mistake.
---

# Memory Update

Use when a durable decision, risk, outcome, or repeated lesson will help future
contributors. Do not create process records merely to authorize work.

## Update As Applicable

- `.commitrail/INDEX.md` for durable initiative disposition or next boundary
- initiative `OVERVIEW.md` for durable multi-PR context
- the current change record for material evidence, findings, risks, or decisions
- an owning specification or ADR when the fact is product or architecture truth

## Capture

- What was completed
- What was merged/rejected/blocked
- PR links
- Remaining risks
- Follow-up items
- Repeated agent mistakes
- Policy/skill improvements needed

## Rules

- Durable repository records are preferable to decisions buried only in chat.
- Do not bury decisions in conversation only.
- If a repeated issue appears, suggest policy/skill update.
- Memory is context, not an authorization mechanism and not a prerequisite for
  branching, implementation, or opening a pull request.
- Update the smallest applicable record in the same pull request as the change.
  Do not create a second post-merge memory PR. Git and GitHub remain the source
  of truth for commits, checks, reviews, approvals, and merges.
