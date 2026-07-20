# INTENT: WS-ENG-001 - Codex Zero-Trust Loop Bootstrap

## Problem Being Solved

Workstream has been using a strong manual engineering loop: discuss intent,
define chunks, implement narrowly, run tests, run internal reviewers, address
CodeRabbit, and stop for human review. That process is not yet encoded in the
repository in a Codex-native way.

Without durable loop artifacts, new contributors and future Codex sessions must
reconstruct the process from chat history. That creates risk around stale memory,
unclosed sub-agent sessions, missed internal reviewers, vague naming, and
accidental PR or merge behavior.

## Why This Work Matters

Workstream is infrastructure for evaluating and coordinating useful human-agent
work. The way Workstream is built must be as disciplined as the product itself.
The engineering loop should be portable to Workstream first and later reusable
across Jarvis, OmniCoreAgent, and other Flow projects.

## Target Behavior

- Codex can discover Workstream engineering skills from `.agents/skills/`.
- Codex can spawn/read custom reviewer roles from `.codex/agents/`.
- Engineering policies and memory live under `.agent-loop/`.
- CI has a static agent gate and internal review evidence gate.
- PRs carry a trust bundle that makes intent, scope, evidence, reviews, and
  remaining risks easy to inspect.
- The repo clearly states that agents do not merge without explicit user approval.

## Non-Goals

- No Workstream product behavior changes.
- No database schema changes.
- No API changes.
- No frontend implementation.
- No Claude-specific setup.
- No generic framework installation that overwrites Workstream language.

## Human Decisions Required

- Whether this bootstrap structure is the permanent Workstream engineering loop.
- Whether later projects should adopt the same structure directly or through a
  packaged Codex plugin.

## 2026-07-20 Projection Consistency Extension

### Problem being solved

Signed schema-v2 state and `LOOP_STATE.md` correctly recorded AUTH-09E PR #157,
but `automation/loop-memory` retained stale `WORK_QUEUE.md` and AUTH `STATUS.md`
copies describing AUTH-05B because the workflow neither generates nor validates
them.

### Why this work matters

Humans and agents must not receive contradictory completed, stopped, next, or
active state from files presented on the canonical automation branch. The fix
must preserve the removal of manual post-merge memory PRs.

### Current behavior

- A trusted `main` push updates signed `STATE.json`, `MERGE_LOG.jsonl`, and
  deterministic `LOOP_STATE.md`.
- Cloning the existing automation branch preserves unrelated legacy files.
- State-root validation ignores those files.
- A merge event records completion but cannot prove a later human start that
  exists only in conversation or an unmerged worktree.

### Target behavior and design chosen

Split the repair into `WS-ENG-001-04A` for complete merge projections and
`WS-ENG-001-04B` for explicit-start events. Every canonical Markdown view is
derived from typed authenticated state. Authored initiative histories on `main`
remain reviewed context rather than automation output.

### Alternatives considered

- Manual memory PRs: rejected as duplicate review of deterministic output.
- Copy authored queue/status files after merge: rejected because mutable prose
  and parallel-work claims are not derivable from one merged PR.
- Treat conversation as automation input: rejected because it is not a durable,
  authenticated repository event.
- Combine merge and start automation: rejected as an oversized write-capable
  workflow change that conflates distinct authorities.

### Boundaries preserved

Protected `main`, explicit human merge approval, initiative-local successors,
signature verification, trusted-main execution, fixed branch writes, and all
implementation/reviewer gates remain unchanged.

### Expected risks and non-goals

The main risks are signing an incomplete projection set, unsafe cleanup,
misrepresenting one last merge as every initiative's state, or permitting a
stale/unauthenticated start. No product behavior, schema, migration, dependency,
coverage threshold, PR approval, or merge authority changes.

### Proof and human decisions

Fixture-driven Git-tree rebuild, signature-tamper, unexpected-file, interleaved-
initiative, replay, stale-event, renderer, and workflow-structure tests must
pass with at least 90 percent branch coverage for changed loop-memory scripts.
The user must approve 04A implementation after planning review, then separately
approve 04B only after 04A merge and replay proof.
