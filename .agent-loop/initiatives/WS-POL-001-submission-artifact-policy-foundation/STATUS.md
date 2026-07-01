# Status: WS-POL-001 - Submission Artifact Policy Foundation

## Current Status

`WS-POL-001-01` is merged to `main`. `WS-POL-001-02` is implemented on branch
`codex/ws-pol-001-02-agent-runtime-compiler`; PR #61 is ready for user review.

Internal review and deterministic proof are complete for reviewed code SHA
`89420d15184d6ff00b13a537d81de94e0703f3af`. External review and GitHub Actions
are complete on final branch head `1ce3fed5c4e562d20a35cc498f1bf42a665579eb`.
The current gate is user review.

## Active Chunk

`WS-POL-001-02` - Async Guide Analysis And Policy Derivation

## Chunk Status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-POL-001-01` | Merged | `codex/ws-pol-001-01-submission-artifact-policy` | 28 | Implements guide-source snapshots, guide sufficiency reports, submission artifact policy, effective project policy, project pre-submit checker contract, activation guards, and key-based artifact policy merge. |
| `WS-POL-001-02` | Ready for user review | `codex/ws-pol-001-02-agent-runtime-compiler` | 61 | Adds async guide sufficiency / derivation agents, runtime port, OpenAI adapter boundary, trusted compiler path, and server-owned provenance guards. |
| `WS-POL-001-03` | Planned | - | - | Moves task locked-context and submission runtime to the effective policy and project checker bundle. |
| `WS-POL-001-04` | Planned | - | - | Splits post-submit checker policy provenance. |
| `WS-POL-001-05` | Planned | - | - | Proves revision resubmission and real API drill. |

## Blockers

| Blocker | Owner | Next action |
|---|---|---|
| User review | User | Review PR #61 and decide whether to merge. |

## Follow-Ups

| Item | Source | Priority |
|---|---|---|
| Add task locked guide-source snapshot/effective-policy/pre-submit bundle references before `READY` | Chunk map | High for Chunk 3 |
