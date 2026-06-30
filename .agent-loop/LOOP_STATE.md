# Loop State

## Current State

- Active initiative: `WS-POL-001` - Submission Artifact Policy Foundation
- Active planning chunk: none
- Active implementation chunk: `WS-POL-001-02`
- Branch: `codex/ws-pol-001-02-agent-runtime-compiler`
- Status: `WS-POL-001-01` merged; `WS-POL-001-02` implementation complete with internal review and evidence gate passed
- Reviewed code SHA: `c2f79b835a1bb033ffffca79ec507b77efcaae3b`
- Current gate: publish PR, run external review, then wait for human checkpoint
- Next chunk: inactive until `WS-POL-001-02` is reviewed and merged by the user

## Operating Rule

Workstream engineering chunks move through:

```text
Intent -> Discovery -> Plan -> Chunk Map -> Chunk Contract -> Implementation -> Evidence -> Internal Review -> PR -> Human Checkpoint -> Memory Update -> Stop
```

This branch implements the second backend foundation chunk for submission intake
policy. It introduces the agent runtime boundary, first OpenAI adapter, async
guide analysis/derivation orchestration, and trusted compiler path. It does not
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
- External review response is tracked separately at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-01-external-review-response.md`.
