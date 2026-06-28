# Status: WS-POL-001 - Submission Artifact Policy Foundation

## Current Status

`WS-POL-001-01` implementation is complete locally on branch
`codex/ws-pol-001-01-submission-artifact-policy`.

Internal reviewer fanout is complete for reviewed code SHA
`a77845bfe041c3fa8d7f9b25b928e76060049ec2`. Deterministic local checks,
internal evidence validation, GitHub Actions, and CodeRabbit passed. The current
gate is explicit user review and merge approval for PR #28.

## Active Chunk

`WS-POL-001-01` - Guide Policy Bundle Foundation

## Chunk Status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-POL-001-01` | External review complete; awaiting explicit user approval | `codex/ws-pol-001-01-submission-artifact-policy` | 28 | Implements guide-source snapshots, guide sufficiency reports, submission artifact policy, effective project policy, project pre-submit checker contract, activation guards, and key-based artifact policy merge. |
| `WS-POL-001-02` | Planned | - | - | Adds async guide sufficiency / derivation agents and the trusted compiler path. |
| `WS-POL-001-03` | Planned | - | - | Moves task locked-context and submission runtime to the effective policy and project checker bundle. |
| `WS-POL-001-04` | Planned | - | - | Splits post-submit checker policy provenance. |
| `WS-POL-001-05` | Planned | - | - | Proves revision resubmission and real API drill. |

## Blockers

| Blocker | Owner | Next action |
|---|---|---|
| Human merge decision | User | Review PR #28 trust bundle and approve merge only if acceptable. |

## Follow-Ups

| Item | Source | Priority |
|---|---|---|
| Replace test/E2E direct compiled-field mutation with real trusted compiler path | Reuse/dedup, architecture, and product/ops review | High for Chunk 2 |
| Define artifact/evidence key grammar before compiler/runtime consumption | Senior engineering and QA review | High for Chunk 2 |
| Decide whether `required` remains boolean or becomes `Literal[True]` | Senior engineering review | High for Chunk 2 |
| Make sufficiency report creation draft-only and warning acknowledgement idempotent | Security review | Medium |
| Add task locked guide-source snapshot/effective-policy/pre-submit bundle references before `READY` | Chunk map | High for Chunk 3 |
