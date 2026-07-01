# Status: WS-POL-001 - Submission Artifact Policy Foundation

## Current Status

`WS-POL-001-01` is merged to `main`. `WS-POL-001-02` is implemented on branch
`codex/ws-pol-001-02-agent-runtime-compiler`; PR #61 is ready for user review
after final evidence-only check rerun.

Internal review and deterministic proof are complete for reviewed code SHA
`aaffa7b25d88fcdff9a87e89d6a2f7ff6ceabb46`. External review and GitHub Actions
passed on pushed head `d7e4669f6fa6bd782a8f12e43bb5b94449fb235d`: CodeRabbit,
Agent Gates, Backend, and Week 1 API Demo UI are green, and no unresolved
non-outdated review threads remain.

## Active Chunk

`WS-POL-001-02` - Async Guide Analysis And Policy Derivation

## Chunk Status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-POL-001-01` | Merged | `codex/ws-pol-001-01-submission-artifact-policy` | 28 | Implements guide-source snapshots, guide sufficiency reports, submission artifact policy, effective project policy, project pre-submit checker contract, activation guards, and key-based artifact policy merge. |
| `WS-POL-001-02` | External review passed | `codex/ws-pol-001-02-agent-runtime-compiler` | 61 | Adds async guide sufficiency / derivation agents, runtime port, OpenAI Agents SDK adapter boundary, trusted compiler path, and server-owned provenance guards. |
| `WS-POL-001-03` | Planned | - | - | Moves task locked-context and submission runtime to the effective policy and project checker bundle. |
| `WS-POL-001-04` | Planned | - | - | Splits post-submit checker policy provenance. |
| `WS-POL-001-05` | Planned | - | - | Proves revision resubmission and real API drill. |

## Blockers

| Blocker | Owner | Next action |
|---|---|---|
| User review | User | Review PR #61 after the final evidence-only check rerun and decide whether to merge. |

## Follow-Ups

| Item | Source | Priority |
|---|---|---|
| Add task locked guide-source snapshot/effective-policy/pre-submit bundle references before `READY` | Chunk map | High for Chunk 3 |
