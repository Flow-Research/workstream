---
name: external-review-response
description: Triage and respond to external reviewer comments such as CodeRabbit, GitHub checks, or human PR review comments.
---

# External Review Response

Use after external reviewer comments arrive.

External review is separate from internal sub-agent review evidence. Write
external review responses to:

```text
.agent-loop/initiatives/<initiative>/reviews/<chunk-id>-external-review-response.md
```

Do not put CodeRabbit, GitHub checks, or human PR review findings inside
`*-internal-review-evidence.md`. Internal evidence proves the Codex sub-agent
review loop; external response files prove how PR review feedback was handled.

## Process

1. Group comments by severity and theme.
2. Decide whether each comment is in scope for the current chunk.
3. Fix clear in-scope issues with the smallest defensible change.
4. Defer out-of-scope issues to follow-up only with explanation.
5. Escalate architecture/product/security judgments to human.
6. Rerun relevant checks.
7. Update the external review response artifact.
8. Update PR trust bundle and review log.

## Output

```text
Comments addressed:
Comments deferred:
Human decisions needed:
Commands rerun:
Remaining risks:
```
