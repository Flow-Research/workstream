# Chunk Contract: WS-CI-003-01 Atomic Chunk State

## Goal

Ensure a human merge atomically lands both the bounded change and its durable
chunk/initiative state, without a pre-merge memory PR or post-merge repair PR.

## Why this chunk exists

PR #318 had to reconcile state after earlier chunks merged, and its own
`WS-ARCH-001-HK1` row still landed as `In review`. The repository had no gate
requiring changed chunk contracts and their projections to describe the state
that would exist after merge.

## Risk class

L1 CI and contributor workflow.

## Allowed files

```text
.github/workflows/agent-gates.yml
.github/pull_request_template.md
AGENTS.md
CONTRIBUTING.md
scripts/check_chunk_state_sync.py
scripts/test_chunk_state_sync.py
scripts/test_lightweight_agent_gates.py
.agent-loop/CURRENT_STATE.md
.agent-loop/templates/PR_TRUST_BUNDLE.md
.agent-loop/initiatives/WS-CI-002-deterministic-agent-gates/STATUS.md
.agent-loop/initiatives/WS-CI-003-atomic-chunk-state/**
```

## Not allowed

- Post-merge commits, automated merge PRs, direct pushes, or write tokens.
- Product, schema, authorization, dependency, test-selection, coverage, or
  branch-protection changes.
- Inferring completion from historical review files or chat.
- More than one implementation chunk in one PR.

## Acceptance criteria

- [x] Implementation-surface changes require exactly one changed chunk contract.
- [x] Every changed chunk contract declares one final outcome on merge.
- [x] The same PR changes its initiative `CHUNK_MAP.md`, initiative `STATUS.md`,
      and `.agent-loop/CURRENT_STATE.md`.
- [x] All three projections name the exact chunk and final outcome.
- [x] A completed chunk cannot remain `in review`, `pending review`, or
      `ready for review` in its chunk-map row.
- [x] Planning, completion, cancellation, and supersession are supported.
- [x] GitHub review and human merge remain the only approval and merge steps.
- [x] No post-merge automation is introduced.

## Merge state

- Outcome on merge: `complete`

## Verification

```bash
python3 -m unittest -v scripts.test_chunk_state_sync scripts.test_lightweight_agent_gates
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

## Required review

CI integrity and documentation review. Human review should confirm the rule is
atomic, deterministic, and does not introduce a second merge workflow.
