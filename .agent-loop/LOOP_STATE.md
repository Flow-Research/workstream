# Loop State

## Current State

- Active initiative: `WS-POL-001` - Submission Artifact Policy Foundation
- Active planning chunk: `WS-POL-001-01` - Submission Artifact Policy Foundation
- Branch: `codex/submission-artifact-policy-loop-plan`
- Status: intent, discovery, plan, chunk map, and first chunk contract drafted; implementation has not started
- Merge commit: none for this initiative
- Reviewed code SHA: pending refresh after latest internal-review fixes
- Current gate: internal review evidence refresh before human review of plan and first chunk contract; backend implementation is not approved
- Next chunk: inactive until `WS-POL-001-01` is approved and completed

## Operating Rule

Workstream engineering chunks move through:

```text
Intent -> Discovery -> Plan -> Chunk Map -> Chunk Contract -> Implementation -> Evidence -> Internal Review -> PR -> Human Checkpoint -> Memory Update -> Stop
```

The current initiative is Workstream product planning for submission intake
policy. The current branch changes loop planning artifacts only; it does not
change Workstream product behavior, database schema, API behavior, or frontend
behavior.

## Last Review State

- Last completed initiative: `WS-ENG-001` Codex zero-trust engineering loop bootstrap.
- PR #23 merged into `main` on 2026-06-20.
- PR #24 updated post-merge loop memory on `main`.
- PR #25 added Terminal Benchmark example material under `examples/`.
- Current planning branch has internal review evidence at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-01-internal-review-evidence.md`; evidence is being refreshed for the latest reviewed revision.
