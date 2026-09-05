---
name: intent-ledger
description: Capture human intent, rationale, non-goals, alternatives, boundaries, and proof strategy before implementation.
---

# Intent Ledger

Use this before code is written and again before PR creation.

Reuse the current Commitrail change record or overview. These are content
questions, not a requirement for another file, repeated prose, or approval gate.

## Required sections

```text
Problem being solved
Why this work matters
Current behavior
Target behavior
Design chosen
Alternatives considered
Boundaries preserved
Expected risks
What must not change
How this will be proven
Human decisions required
```

## Rules

- Intent must be human-readable.
- Do not hide uncertainty.
- State non-goals explicitly.
- If the agent is unsure, ask or mark as assumption.
- The intent ledger should make the future diff easier to review.
