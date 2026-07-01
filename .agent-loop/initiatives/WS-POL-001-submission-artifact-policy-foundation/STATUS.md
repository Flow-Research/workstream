# Status: WS-POL-001 - Submission Artifact Policy Foundation

## Current Status

`WS-POL-001-01` is merged to `main`. `WS-POL-001-02` is implemented on branch
`codex/ws-pol-001-02-agent-runtime-compiler`.

Internal review and deterministic proof are complete for reviewed code SHA
`66fb9936c0a9f7fa04bbe783483dbdff0cfb5eb3`. The current gate is evidence-gate
rerun, reviewed branch push, external review, and human checkpoint.

## Active Chunk

`WS-POL-001-02` - Async Guide Analysis And Policy Derivation

## Chunk Status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-POL-001-01` | Merged | `codex/ws-pol-001-01-submission-artifact-policy` | 28 | Implements guide-source snapshots, guide sufficiency reports, submission artifact policy, effective project policy, project pre-submit checker contract, activation guards, and key-based artifact policy merge. |
| `WS-POL-001-02` | Internal review complete; evidence finalizing | `codex/ws-pol-001-02-agent-runtime-compiler` | - | Adds async guide sufficiency / derivation agents, runtime port, OpenAI adapter boundary, trusted compiler path, and server-owned provenance guards. |
| `WS-POL-001-03` | Planned | - | - | Moves task locked-context and submission runtime to the effective policy and project checker bundle. |
| `WS-POL-001-04` | Planned | - | - | Splits post-submit checker policy provenance. |
| `WS-POL-001-05` | Planned | - | - | Proves revision resubmission and real API drill. |

## Blockers

| Blocker | Owner | Next action |
|---|---|---|
| External PR review | Codex | Run evidence gates, push the reviewed branch, and wait for CodeRabbit/GitHub Actions before human checkpoint. |

## Follow-Ups

| Item | Source | Priority |
|---|---|---|
| Add task locked guide-source snapshot/effective-policy/pre-submit bundle references before `READY` | Chunk map | High for Chunk 3 |
