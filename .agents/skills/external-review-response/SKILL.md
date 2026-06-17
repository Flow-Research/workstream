---
name: external-review-response
description: Triage and respond to external reviewer comments such as CodeRabbit, GitHub Copilot review, Greptile, or human review comments.
---

# External Review Response

Use after external reviewer comments arrive.

## Process

1. Group comments by severity and theme.
2. Decide whether each comment is in scope for the current chunk.
3. Fix clear in-scope issues with the smallest defensible change.
4. Defer out-of-scope issues to follow-up only with explanation.
5. Escalate architecture/product/security judgments to human.
6. Rerun relevant checks.
7. Update PR trust bundle and review log.

## Output

```text
Comments addressed:
Comments deferred:
Human decisions needed:
Commands rerun:
Remaining risks:
```
