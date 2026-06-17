# DECISIONS: WS-ENG-001

## Accepted

- Use `.agents/skills/` for repo-scoped Codex skills.
- Use `.codex/agents/` for Codex custom reviewer agents.
- Use `.agent-loop/` for durable engineering memory and evidence.
- Do not copy Claude-specific files into Workstream in this bootstrap.
- Add Product/Ops as a first-class reviewer track.
- Preserve existing `docs/internal_reviews/` evidence compatibility.

## Deferred

- Packaging the loop as a reusable Codex plugin for other Flow projects.
- Adding hooks that block local PR creation before evidence exists.
- Automating reviewer fanout beyond Codex's explicit subagent workflow.
