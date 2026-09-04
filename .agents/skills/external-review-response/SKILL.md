---
name: external-review-response
description: Triage and respond to external reviewer comments such as CodeRabbit, GitHub checks, or human PR review comments.
---

# External Review Response

Use after external reviewer comments arrive.

External review is separate from private internal-review receipts. Record
material external findings and dispositions in the current Commitrail change
record or PR conversation. Create a separate response record only when the
volume or risk makes it independently useful; never do so ceremonially.

## Process

1. Group comments by severity and theme.
2. Decide whether each comment is in scope for the current chunk.
3. Fix clear in-scope issues with the smallest defensible change.
4. Defer out-of-scope issues to follow-up only with explanation.
5. Escalate architecture/product/security judgments to human.
6. Rerun relevant checks.
7. Update the current change record when the finding materially changes its
   design, risk, evidence, or remaining uncertainty.
8. Update the PR trust summary without duplicating transient GitHub state.

## Output

```text
Comments addressed:
Comments deferred:
Human decisions needed:
Commands rerun:
Remaining risks:
```
