---
name: pr-trust-bundle
description: Create a human-readable PR trust bundle containing intent, design, scope, tests, CI integrity, reviewer results, risks, and human review focus.
---

# PR Trust Bundle

Create the PR body or trust bundle after implementation and review.

## Canonical format

Use `.github/pull_request_template.md`; do not invent a second twenty-section
report. Link the combined Commitrail record for durable intent, boundaries,
design, acceptance criteria, and remaining risks. Keep current diff, command
results, exact-head review freshness, CI, and external conversations in the PR.

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
- After a push, mark affected old results historical until replayed. Never just
  replace a SHA while keeping old reviewer results. Description-only corrections
  do not change the code target or require rerunning unaffected runtime tests.
- Summarize proof quality by behavior boundary, proof strength/custody,
  compatibility, discriminating probe, and uncertainty. Never copy private
  session receipts into Git or imply that a summary owns their custody.
