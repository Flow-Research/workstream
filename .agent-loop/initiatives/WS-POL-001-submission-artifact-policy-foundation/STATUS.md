# Status: WS-POL-001 - Submission Artifact Policy Foundation

## Current Status

`WS-POL-001-01` is merged to `main`. `WS-POL-001-02` is implemented on branch
`codex/ws-pol-001-02-agent-runtime-compiler`.

Internal review, deterministic proof, and the internal review evidence gate have
passed for reviewed code SHA `c2f79b835a1bb033ffffca79ec507b77efcaae3b`.
The current gate is PR publication, external review, and human checkpoint.

## Active Chunk

`WS-POL-001-02` - Async Guide Analysis And Policy Derivation

## Chunk Status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-POL-001-01` | Merged | `codex/ws-pol-001-01-submission-artifact-policy` | 28 | Implements guide-source snapshots, guide sufficiency reports, submission artifact policy, effective project policy, project pre-submit checker contract, activation guards, and key-based artifact policy merge. |
| `WS-POL-001-02` | Internal review complete; ready for PR | `codex/ws-pol-001-02-agent-runtime-compiler` | - | Adds async guide sufficiency / derivation agents, runtime port, OpenAI adapter boundary, and the trusted compiler path. |
| `WS-POL-001-03` | Planned | - | - | Moves task locked-context and submission runtime to the effective policy and project checker bundle. |
| `WS-POL-001-04` | Planned | - | - | Splits post-submit checker policy provenance. |
| `WS-POL-001-05` | Planned | - | - | Proves revision resubmission and real API drill. |

## Blockers

| Blocker | Owner | Next action |
|---|---|---|
| External PR review | Codex | Publish the reviewed branch, open PR, and wait for CodeRabbit/GitHub Actions before human checkpoint. |

## Follow-Ups

| Item | Source | Priority |
|---|---|---|
| Replace test/E2E direct compiled-field mutation with real trusted compiler path | Reuse/dedup, architecture, and product/ops review | High for Chunk 2 |
| Define artifact/evidence key grammar before compiler/runtime consumption | Senior engineering and QA review | High for Chunk 2 |
| Decide whether `required` remains boolean or becomes `Literal[True]` | Senior engineering review | High for Chunk 2 |
| Make sufficiency report creation draft-only and warning acknowledgement idempotent | Security review | Medium |
| Add task locked guide-source snapshot/effective-policy/pre-submit bundle references before `READY` | Chunk map | High for Chunk 3 |
