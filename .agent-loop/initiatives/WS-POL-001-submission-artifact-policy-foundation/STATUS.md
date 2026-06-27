# Status: WS-POL-001 - Submission Artifact Policy Foundation

## Current Status

`WS-POL-001-01` implementation is complete locally on branch
`codex/ws-pol-001-01-submission-artifact-policy`.

Internal reviewer fanout is complete for reviewed code SHA
`de41f8701eb2ce98b2e355d984c60d9c0a0e7a34`. Deterministic local checks passed.
The current gate is PR creation and external review.

## Active Chunk

`WS-POL-001-01` - Guide Policy Bundle Foundation

## Chunk Status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-POL-001-01` | Internal review complete; PR pending | `codex/ws-pol-001-01-submission-artifact-policy` | - | Implements guide-source snapshots, guide sufficiency reports, submission artifact policy, effective project policy, project pre-submit checker contract, and activation guards. |
| `WS-POL-001-02` | Planned | - | - | Adds async guide sufficiency / derivation agents and the trusted compiler path. |
| `WS-POL-001-03` | Planned | - | - | Moves task locked-context and submission runtime to the effective policy and project checker bundle. |
| `WS-POL-001-04` | Planned | - | - | Splits post-submit checker policy provenance. |
| `WS-POL-001-05` | Planned | - | - | Proves revision resubmission and real API drill. |

## Blockers

| Blocker | Owner | Next action |
|---|---|---|
| External review | Codex/user | Open PR, wait for GitHub checks and CodeRabbit, then address valid findings. |
| Human merge decision | User | Review PR trust bundle and approve merge only if acceptable. |

## Follow-Ups

| Item | Source | Priority |
|---|---|---|
| Replace test/E2E direct compiled-field mutation with real trusted compiler path | Reuse/dedup and product/ops review | High for Chunk 2 |
| Add task locked guide-source snapshot/effective-policy/pre-submit bundle references before `READY` | Chunk map | High for Chunk 3 |
| Reuse activation-strength validation for active-guide reads before task locked-context consumes active-guide output | Senior engineering review | Medium |
| Map duplicate source-snapshot bundle conflicts to a clean API response or idempotent return | Senior engineering review | Medium |
