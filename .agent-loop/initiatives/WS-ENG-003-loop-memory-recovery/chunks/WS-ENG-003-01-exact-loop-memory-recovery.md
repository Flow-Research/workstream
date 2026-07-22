# Chunk Contract: WS-ENG-003-01 — Exact Loop Memory Recovery

## Parent initiative

WS-ENG-003 — Loop Memory Recovery

## Goal

Reconcile PR #166 and this recovery merge exactly once, then restore ordinary enforcement.

## Why this chunk exists

The start-mechanism migration could not use the mechanism it introduced.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ENG-003-loop-memory-recovery/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ENG-003-loop-memory-recovery/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ENG-003-loop-memory-recovery/CHUNK_MAP.md`

## Risk class

L1

## SLA

P0

## Allowed files

```text
.github/workflows/loop-memory.yml
scripts/update_post_merge_memory.py
scripts/test_update_post_merge_memory.py
scripts/test_check_loop_memory_state.py
scripts/test_agent_gates.py
.agent-loop/policies/loop-memory-recovery.json
.agent-loop/initiatives/WS-ENG-003-loop-memory-recovery/**
.agent-loop/merge-intents/WS-ENG-003-01.json
docs/operations_post_merge_memory.md
```

## Not allowed

```text
Manual automation-branch edits or force pushes
Wildcard, reusable, actor-only, or unsigned exemptions
Changes to normal start/cancel authorization
Product, API, database, dependency, or signing-key changes
Merge without explicit user approval for the recovery PR
```

## Acceptance criteria

- [ ] Recovery activates only when the exact workflow target is a merged `WS-ENG-003-01` record.
- [ ] The resolved target is the final planned merge and the plan is exactly PR #166 followed by recovery.
- [ ] PR #166 is matched by exact initiative, chunk, PR number, and merge SHA.
- [ ] The recovery PR exemption uses its GitHub-derived exact PR number.
- [ ] Both recovery exemptions are consumed in order and none persists afterward.
- [ ] Unrelated legacy exemptions are preserved and later unstarted merges still fail.
- [ ] Replay remains idempotent and canonical state validates.
- [ ] Wrong/later/non-final targets, collisions, partial consumption, and ambiguous GitHub evidence fail closed before publication.

## Verification commands

```bash
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py
python3 scripts/test_agent_gates.py
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

Verify exact activation, exact two-entry consumption, and that no reusable bypass survives.

## Stop conditions

Stop if recovery requires unsigned/manual state, a wildcard exemption, a new secret, force push, or weakened normal enforcement.
