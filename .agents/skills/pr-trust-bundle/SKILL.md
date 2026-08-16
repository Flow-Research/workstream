---
name: pr-trust-bundle
description: Create a human-readable PR trust bundle containing intent, design, scope, tests, CI integrity, reviewer results, risks, and human review focus.
---

# PR Trust Bundle

Create the PR body or trust bundle after implementation and review.

## Required sections

- Chunk
- Goal
- Human-approved intent
- What changed
- Why it changed
- Design chosen
- Alternatives rejected
- Scope control
- Product behavior
- Acceptance criteria proof
- Tests/checks run
- Test delta
- CI integrity
- Reviewer results
- External review
- Remaining risks
- Follow-up work
- Human review focus
- Human merge ownership

## Rules

- Be concise but complete.
- Do not paste huge logs; summarize and cite commands.
- Distinguish evidence from claims.
- Make review easier for a human who has not followed the chat.
- Label each external result as `fresh substantive review`, `not fresh`, or
  `unavailable`. A green status produced by a skipped, rate-limited, or
  manual-trigger-required review is `not fresh`, never reviewer approval.
- Internal reviewer summaries are non-authoritative mirrors of private session
  receipts and must name the exact reviewed head.
