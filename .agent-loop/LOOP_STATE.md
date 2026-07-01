# Loop State

## Current State

- Active initiative: `WS-POL-001` - Submission Artifact Policy Foundation
- Active planning chunk: none
- Active implementation chunk: `WS-POL-001-02`
- Branch: `codex/ws-pol-001-02-agent-runtime-compiler`
- Status: `WS-POL-001-01` merged; `WS-POL-001-02` internal review and external review passed
- Reviewed code SHA: `aaffa7b25d88fcdff9a87e89d6a2f7ff6ceabb46`
- Current gate: final evidence-only check rerun, then user review for PR #61
- Next chunk: inactive until `WS-POL-001-02` is reviewed and merged by the user

## Operating Rule

Workstream engineering chunks move through:

```text
Intent -> Discovery -> Plan -> Chunk Map -> Chunk Contract -> Implementation -> Evidence -> Internal Review -> PR -> Human Checkpoint -> Memory Update -> Stop
```

This branch implements the second backend foundation chunk for submission intake
policy. It introduces the agent runtime boundary, first OpenAI Agents SDK
adapter, async guide analysis/derivation orchestration, and trusted compiler
path. It does not
implement task locked-context migration, submission runtime migration, frontend
behavior, payment, reputation, settlement, or blockchain integrations.

## Last Review State

- Last completed initiative: `WS-ENG-001` Codex zero-trust engineering loop bootstrap.
- PR #23 merged into `main` on 2026-06-20.
- PR #24 updated post-merge loop memory on `main`.
- PR #25 added Terminal Benchmark example material under `examples/`.
- PR #26 approved and merged WS-POL-001 planning into `main` on 2026-06-27.
- PR #27 updated WS-POL post-merge memory on `main`.
- PR #28 implemented `WS-POL-001-01` and was merged into `main`.
- Current implementation branch: `codex/ws-pol-001-02-agent-runtime-compiler`.
- Internal review evidence for the active chunk is at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-02-internal-review-evidence.md`.
- PR trust bundle for the active chunk is at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-02-pr-trust-bundle.md`.
- External review response for the active chunk is tracked separately at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-02-external-review-response.md` after external review runs.
- PR #61 is open. External review and CI passed on pushed head
  `d7e4669f6fa6bd782a8f12e43bb5b94449fb235d`; after this evidence-only update
  reruns checks, the next gate is the user-owned merge decision.
