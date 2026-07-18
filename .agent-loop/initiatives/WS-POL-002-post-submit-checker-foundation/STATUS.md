# Status: WS-POL-002 - Post-Submit Checker Foundation

## Current Status

Planning completed and merged through PR #85 as
`3fc1a688743f13476d6092078d40792592823d27`.

Chunk 03 merged through PR #90 as `a7aa474` on 2026-07-11. This authorization
worktree only reconciles that merged behavior with the active authorization
baseline. Post-merge memory merged through PR #94 as `b1270d7`. No later chunk
may start until the relevant authorization foundation exists and the user
provides a separate explicit start signal.
`WS-POL-002-01` merged through PR #87 as `ed52c21` on 2026-07-09. It
implemented the version-stamped trusted post-submit compiler contract,
default-checker snapshot validation, canonical policy hashing, and tests around
default-drift safety.

`WS-POL-002-02` merged through PR #88 as `32af6a7` on 2026-07-11. It
implemented setup-time post-submit checker derivation, resumable setup
continuation, generated project `PostSubmitCheckerPolicy` persistence, automatic
contributor submission handoff to the pre-review gate, and repair-only
`/finalize` semantics.

`WS-POL-002-03` merged through PR #90 as `a7aa474` on 2026-07-11. It
implemented server-owned post-submit checker policy approval and correction,
append-only correction history, exact-context replacement linkage, immutable
approval provenance, and bounded setup visibility APIs. Required internal
review, CodeRabbit, and GitHub checks passed before the explicit human merge.

## Active Planning Chunk

None.

## Active Implementation Chunk

None. `WS-POL-002-04` remains inactive until authorization proof and a separate
explicit user start.

## Current Implementation Branch

None for implementation. Post-merge memory is complete through PR #94.

## Chunk Status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-POL-002-PLAN` | Merged | `codex/ws-pol-002-post-submit-checker-planning` | #85 | Defines intent, discovery, design, risks, decisions, and implementation chunks. |
| `WS-POL-002-01` | Merged | `codex/ws-pol-002-01-post-submit-compiler` | #87 | Post-Submit Compiler Contract; merged as `ed52c21`. |
| `WS-POL-002-02` | Merged | `codex/ws-pol-002-02-post-submit-derivation` | #88 | Post-submit derivation agent and resumable setup integration; merged as `32af6a7`. |
| `WS-POL-002-03` | Merged | `codex/ws-pol-002-03-post-submit-approval-visibility` | #90 | Server-owned approval, correction audit history, and setup visibility APIs; merged as `a7aa474`. |
| `WS-POL-002-04` | Inactive | - | - | Runtime hardening remains gated by authorization proof and a separate user start. |
| `WS-POL-002-05` | Proposed | - | - | Terminal Benchmark-style live API proof and report. |

## Blockers

| Blocker | Owner | Next action |
|---|---|---|
| `WS-AUTH-001` foundation | Authorization proof must precede chunk 04 runtime hardening | Complete the relevant auth cutover, then require an explicit chunk 04 start |
