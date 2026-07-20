# Chunk Contract: WS-ENG-001-04B - Signed Explicit Start Events

## Parent initiative

`WS-ENG-001` - Codex Zero-Trust Loop Bootstrap

## Goal

Record a protected human start as authenticated loop state and regenerate the
same canonical projections without a bookkeeping PR or automatic successor
activation.

## Risk classification

L1/P1 architecture, CI/workflow, signed authority, test, and documentation.

## Preconditions

- `WS-ENG-001-04A` merged and replay proved all projections consistent.
- A separate explicit human start approved 04B implementation.
- Preimplementation review resolves the deferred actor authorization,
  environment protection, event schema, and mandatory signed cancel/correct
  semantics for mistaken, rejected, or abandoned starts.

## Provisional allowed files

```text
AGENTS.md
.agents/skills/memory-update/SKILL.md
.agent-loop/policies/repository-engineering-policy.md
.agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/**
.agent-loop/merge-intents/WS-ENG-001-04B.json
.github/workflows/loop-memory-start.yml
.github/workflows/loop-memory.yml
docs/operations_post_merge_memory.md
scripts/update_post_merge_memory.py
scripts/check_loop_memory_state.py
scripts/test_agent_gates.py
```

## Not allowed

Product runtime, schema/migrations, automatic start after merge, arbitrary or
cross-initiative selection, chat-derived authority, PR-head execution with
write credentials, direct `main` writes, automated PR approval/merge, or start
of a second chunk while the same initiative is active.

## Acceptance criteria

- Only a protected, attributable human workflow event can start work.
- The requested chunk equals the signed same-initiative successor and its exact
  contract exists on current protected `main`.
- The event records actor, timestamp, protected-main SHA, initiative, and chunk
  in authenticated typed state.
- Replay, stale SHA, unauthorized actor, conflicting active state, arbitrary
  chunk, and cross-initiative selection fail closed.
- All canonical projections update atomically and identify the active chunk.
- A later trusted merge closes that exact active chunk and returns the
  initiative to a stopped successor gate.
- Merge completion must match the authenticated active chunk before clearing it.
- An attributable protected human cancel/correct event records reason and
  evidence, resists replay, and deterministically returns or replaces active
  state without rewriting history.
- No manual bookkeeping PR is required.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Stop condition

This contract is proposed only. Do not resolve provisional design questions or
implement start-event behavior before 04A merge/replay and a separate explicit
human start.
