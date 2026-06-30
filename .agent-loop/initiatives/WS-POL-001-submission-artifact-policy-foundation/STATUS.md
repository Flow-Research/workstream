# Status: WS-POL-001 - Submission Artifact Policy Foundation

## Current Status

`WS-POL-001-01` is merged to `main`. `WS-POL-001-02` is starting on branch
`codex/ws-pol-001-02-agent-runtime-compiler`.

The current gate is Chunk 2 implementation under its approved chunk contract.

## Active Chunk

`WS-POL-001-02` - Async Guide Analysis And Policy Derivation

## Chunk Status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-POL-001-01` | Merged | `codex/ws-pol-001-01-submission-artifact-policy` | 28 | Implements guide-source snapshots, guide sufficiency reports, submission artifact policy, effective project policy, project pre-submit checker contract, activation guards, and key-based artifact policy merge. |
| `WS-POL-001-02` | In progress | `codex/ws-pol-001-02-agent-runtime-compiler` | - | Adds async guide sufficiency / derivation agents, runtime port, OpenAI adapter boundary, and the trusted compiler path. |
| `WS-POL-001-03` | Planned | - | - | Moves task locked-context and submission runtime to the effective policy and project checker bundle. |
| `WS-POL-001-04` | Planned | - | - | Splits post-submit checker policy provenance. |
| `WS-POL-001-05` | Planned | - | - | Proves revision resubmission and real API drill. |

## Blockers

| Blocker | Owner | Next action |
|---|---|---|
| Chunk 2 implementation | Codex | Implement only the allowed WS-POL-001-02 files and run deterministic proof before reviewer fanout. |

## Follow-Ups

| Item | Source | Priority |
|---|---|---|
| Replace test/E2E direct compiled-field mutation with real trusted compiler path | Reuse/dedup, architecture, and product/ops review | High for Chunk 2 |
| Define artifact/evidence key grammar before compiler/runtime consumption | Senior engineering and QA review | High for Chunk 2 |
| Decide whether `required` remains boolean or becomes `Literal[True]` | Senior engineering review | High for Chunk 2 |
| Make sufficiency report creation draft-only and warning acknowledgement idempotent | Security review | Medium |
| Add task locked guide-source snapshot/effective-policy/pre-submit bundle references before `READY` | Chunk map | High for Chunk 3 |
