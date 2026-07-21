# Chunk Contract: WS-ENG-005-01 — Initiative-Local Concurrency

## Parent initiative

`WS-ENG-005` — Parallel Initiative Execution

## Goal

Allow different initiatives to run signed chunks concurrently while retaining
exactly one active chunk per initiative.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ENG-005-parallel-initiative-execution/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ENG-005-parallel-initiative-execution/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ENG-005-parallel-initiative-execution/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
scripts/update_post_merge_memory.py
scripts/check_loop_memory_state.py
scripts/test_update_post_merge_memory.py
scripts/test_check_loop_memory_state.py
scripts/test_agent_gates.py
.agent-loop/policies/loop-memory-recovery.json
.agent-loop/policies/repository-engineering-policy.md
.agent-loop/initiatives/WS-ENG-005-parallel-initiative-execution/**
.agent-loop/merge-intents/WS-ENG-005-01.json
.agent-loop/REVIEW_LOG.md
.agents/skills/memory-update/SKILL.md
AGENTS.md
docs/operations_post_merge_memory.md
```

## Not allowed

```text
More than one active chunk in one initiative
Automatic starts or arbitrary global concurrency cap
Local worktree state as signed authority
Cancellation, signature, ledger, manifest, CI, coverage, or merge-approval weakening
Product, backend API, database, dependency, or workflow changes
Manual automation-branch edits or reusable recovery exemptions
```

## Acceptance criteria

- [ ] AUTH implementation, ART implementation, and CI planning can concurrently
      remain active with no hard-coded pairwise or numeric cap.
- [ ] A second planning or implementation start in either active initiative fails closed.
- [ ] Merge or approved cancellation in multiple orders preserves all other
      active initiatives; A cannot consume B's chunk or reuse B's selection/event.
- [ ] Completed, duplicate, stale-main, stale-tip, malformed-selection, and replay starts remain rejected.
- [ ] Work queue marks every active initiative gate and current gate chunk; loop
      and initiative views show exact active planning/implementation fields;
      ledger replay and independent checker agree.
- [ ] Dispatch publication races remain serialized and require fresh retry after inspection.
- [ ] Docs state one active chunk per initiative and distinguish worktree isolation from signed authority.
- [ ] From real-equivalent AUTH-active state, exact WS-ENG-005-01 bootstrap
      preserves AUTH, consumes itself, then permits ART start. Wrong target,
      extra plan SHA, wrong first parent, replay, and collision fail closed.
- [ ] Updater and checker branch coverage remain at or above 90 percent.

## Verification commands

```bash
ruff check scripts/update_post_merge_memory.py scripts/check_loop_memory_state.py scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py scripts/test_agent_gates.py
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py scripts/test_agent_gates.py
python3 scripts/test_agent_gates.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
```

## Required reviewers

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] CI integrity
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

Verify global serialization is removed consistently, same-initiative exclusion
remains in every trust layer, other active initiatives survive merge/cancel, and
bootstrap authority is exact and self-consuming. Confirm rebase does not
reauthorize scope and post-parallel recovery must remain forward-compatible.

## Stop conditions

Stop if work requires multiple active chunks within one initiative, local
worktree authority, automatic scheduling, a persistent exemption, manual state
editing, new secrets, or weakened tests/controls.
