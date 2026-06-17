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
