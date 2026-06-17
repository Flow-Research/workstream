# Workstream Agent Loop

This directory is durable engineering memory for building Workstream with Codex.

It is not Workstream product state. It records how engineering work is planned,
chunked, reviewed, proven, and handed to a human for merge decisions.

## Codex-Native Surfaces

- `AGENTS.md` contains repository rules that Codex loads before work.
- `.agents/skills/` contains Codex-discoverable workflow skills.
- `.codex/agents/` contains Codex custom reviewer agents.
- `.codex/config.toml` contains repo-scoped Codex settings that load only after
  the repository is trusted.

## Durable Loop Surfaces

- `.agent-loop/policies/` contains Workstream engineering policies.
- `.agent-loop/templates/` contains reusable loop templates.
- `.agent-loop/initiatives/` contains intent, discovery, plans, chunk maps,
  contracts, risks, decisions, and status.
- `.agent-loop/REVIEW_LOG.md` records review outcomes.
- `.agent-loop/WORK_QUEUE.md` records proposed and active engineering chunks.
- `.agent-loop/LOOP_STATE.md` records the current loop state.

## Required Loop

```text
Intent
-> Discovery
-> Plan
-> Chunk Map
-> Chunk Contract
-> Implementation
-> Evidence
-> Internal Review
-> PR
-> Human Checkpoint
-> Memory Update
-> Stop
```

The stop step is intentional. Codex must not begin the next chunk unless the
user explicitly asks for it.
