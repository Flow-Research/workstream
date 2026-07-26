# Workstream Engineering Records

This directory stores durable planning and review context for Workstream. It is
not product state and it is not an authorization database.

Useful records include initiative intent, plans, bounded chunk contracts,
risks, decisions, evidence, and review notes. Historical signed-loop and
recovery artifacts remain only where they help explain earlier decisions; they
do not activate work, lock initiatives, or block pull requests.

The active engineering loop is:

```text
Intent -> Plan -> Bounded Change -> Tests -> Review -> PR -> Human Merge
```

Use the smallest useful artifact. A small change may explain intent and scope
directly in its pull request. Larger or higher-risk work should use an
initiative plan and chunk contract. Different initiatives may run concurrently.

GitHub permissions govern who may contribute. CI validates quality. Human
maintainers decide merges. See [CONTRIBUTING.md](../CONTRIBUTING.md).
