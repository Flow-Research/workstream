# Status: WS-POL-001 - Submission Artifact Policy Foundation

## Current Status

`WS-POL-001-01` is merged to `main`. `WS-POL-001-02` is implemented on branch
`codex/ws-pol-001-02-agent-runtime-compiler`; PR #61 is being updated before it
can return to external review and user review.

Implementation has been updated after the previous reviewed SHA to tighten
runtime adapter naming, config, and guide-source material. Deterministic proof
has passed for the current working tree. Internal review is being rerun before
the branch can return to external review and user review.

## Active Chunk

`WS-POL-001-02` - Async Guide Analysis And Policy Derivation

## Chunk Status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-POL-001-01` | Merged | `codex/ws-pol-001-01-submission-artifact-policy` | 28 | Implements guide-source snapshots, guide sufficiency reports, submission artifact policy, effective project policy, project pre-submit checker contract, activation guards, and key-based artifact policy merge. |
| `WS-POL-001-02` | Internal review rerun | `codex/ws-pol-001-02-agent-runtime-compiler` | 61 | Adds async guide sufficiency / derivation agents, runtime port, OpenAI Agents SDK adapter boundary, trusted compiler path, and server-owned provenance guards. |
| `WS-POL-001-03` | Planned | - | - | Moves task locked-context and submission runtime to the effective policy and project checker bundle. |
| `WS-POL-001-04` | Planned | - | - | Splits post-submit checker policy provenance. |
| `WS-POL-001-05` | Planned | - | - | Proves revision resubmission and real API drill. |

## Blockers

| Blocker | Owner | Next action |
|---|---|---|
| Internal review rerun | Codex | Finish reviewer rerun, update evidence, push PR #61, then wait for external review and user decision. |

## Follow-Ups

| Item | Source | Priority |
|---|---|---|
| Add task locked guide-source snapshot/effective-policy/pre-submit bundle references before `READY` | Chunk map | High for Chunk 3 |
