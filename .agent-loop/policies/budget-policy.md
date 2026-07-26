# Agent Budget Policy

Reviewer fanout should be proportionate to risk.

## Rules

- Keep subagent depth to 1.
- Prefer read-only reviewers for review work.
- Select reviewers based on affected boundaries and risk, not habit.
- Stop after two failed repair cycles for the same blocker.
- Use `gpt-5.5` with high reasoning for Workstream reviewer agents unless the user approves a different model.
- Close completed sub-agent sessions before reporting completion.

## Default Reviewer Set

These rows are routing guidance. Small low-risk changes may use fewer reviewers.

| Work type | Reviewers |
|---|---|
| Engineering-loop/process infra | senior engineering, QA/test, security/auth, product/ops, architecture, CI integrity, docs |
| Product lifecycle/policy | senior engineering, QA/test, security/auth, product/ops, architecture, docs |
| Bug fix | senior engineering, QA/test, test delta when tests change |
| CI/workflow | baseline, CI integrity, reuse/dedup when scripts or agent definitions change |
| Docs-only | docs, product/ops when workflow or operator meaning changes |
