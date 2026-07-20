# Chunk Contract: WS-ENG-001-04B - Signed Explicit Start Events

## Parent initiative

`WS-ENG-001` - Codex Zero-Trust Loop Bootstrap

## Goal

Record a protected human start as authenticated loop state and regenerate the
same canonical projections without a bookkeeping PR or automatic successor
activation.

## Risk routing

- Risk class: L1
- SLA: P1
- Work type: architecture, CI/workflow, signed authority, audit ledger,
  documentation, and tests
- Required reviewers: senior engineering, QA/test, security/auth, product/ops,
  architecture, CI integrity, docs, reuse/dedup, and test delta
- Human gate: required before implementation, protected-environment deployment,
  PR review, and merge
- Budget posture: proof-heavy; start authority, state signatures, and workflow
  credentials require complete fail-closed evidence

## Preconditions

- `WS-ENG-001-04A` merged and replay proved all projections consistent.
- A separate explicit human start approved 04B implementation.
- Preimplementation review resolves the deferred actor authorization,
  environment protection, event schema, and mandatory signed cancel/correct
  semantics for mistaken, rejected, or abandoned starts.

## Allowed files

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
- An attributable protected human cancel event records reason and evidence,
  resists replay, and deterministically returns active state to the same
  successor gate without rewriting history.
- No manual bookkeeping PR is required.
- Start and cancel use a `workflow_dispatch` workflow selected from `main`, run
  only on `refs/heads/main`, with `run_attempt == 1`, shared serialization, a
  fixed state-branch destination, and the protected `loop-memory-start`
  environment.
- The environment-scoped signing secret is unavailable before required human
  approval; repository code documents this external configuration gate.
- Correction is an attributable corrective cancellation restoring the same
  successor gate, followed by a separate protected start; arbitrary replacement
  is absent.
- Legacy already-approved work may still reconcile by merge-only state, but any
  initiative with active signed state must merge that exact chunk.
- Materially changed loop-memory scripts remain at or above 90 percent branch
  coverage.

## Verification commands

```text
python -m pytest -q scripts/test_agent_gates.py
python -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py
python scripts/check_loop_memory_state.py --state-root <fixture-root>
python scripts/check_markdown_links.py
python scripts/check_stale_workstream_wording.py
git diff --check
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Stop condition

Stop if protected environment review cannot gate the signing secret, current
protected `main` cannot be resolved independently, an event would select a
non-successor/cross-initiative chunk, cancellation would rewrite history, or
scope expands into product runtime, automatic merge, or another chunk.
