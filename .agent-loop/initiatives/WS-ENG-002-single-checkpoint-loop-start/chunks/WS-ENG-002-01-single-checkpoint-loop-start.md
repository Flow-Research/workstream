# Chunk Contract: WS-ENG-002-01 — Single-Checkpoint Loop Start

## Parent initiative

WS-ENG-002 — Single-Checkpoint Loop Start

## Goal

Make one authenticated GitHub dispatch sufficient to start the exact declared successor.

## Why this chunk exists

The current environment approval repeats the user's explicit start decision.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ENG-002-single-checkpoint-loop-start/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ENG-002-single-checkpoint-loop-start/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ENG-002-single-checkpoint-loop-start/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
.github/workflows/loop-memory-start.yml
AGENTS.md
docs/operations_post_merge_memory.md
scripts/update_post_merge_memory.py
scripts/check_loop_memory_state.py
scripts/test_update_post_merge_memory.py
scripts/test_check_loop_memory_state.py
.agent-loop/policies/repository-engineering-policy.md
.agent-loop/policies/loop-memory-start-authorities.json
.agent-loop/initiatives/WS-ENG-002-single-checkpoint-loop-start/**
.agent-loop/merge-intents/WS-ENG-002-01.json
```

## Not allowed

```text
Automatic post-merge starts
Signing-key or signature-format changes
Successor, main-SHA, replay, concurrency, or publication weakening
Product, API, database, or dependency changes
Merging without explicit user approval for this PR
```

## Acceptance criteria

- [ ] A first-attempt main-branch dispatch by an authenticated, trusted-main-allowlisted repository writer needs no environment approval; all other writers fail closed.
- [ ] The event records an explicit versioned dispatcher-authority form; historical two-person records remain valid without reinterpretation.
- [ ] Cancellation continues to require the protected environment and distinct reviewer.
- [ ] Actor, main SHA, successor, prior tip, signature, replay, and serialization checks remain enforced.
- [ ] Mixed historical/new ledgers validate, while malformed or forged authority attribution fails closed.
- [ ] When the user says `start`, the orchestrator can dispatch the workflow without requiring a second user action; chat itself is not canonical evidence.
- [ ] Policy and tests describe the single-checkpoint behavior.

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

Confirm that one explicit dispatch replaces only the duplicate environment approval and that signed-state integrity remains unchanged.

## Stop conditions

Stop if implementation requires automatic activation, weaker SHA/successor/signature checks, a new secret, or broader workflow permissions.
