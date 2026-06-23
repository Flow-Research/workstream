# Status: WS-POL-001 - Submission Artifact Policy Foundation

## Current Status

Planning PR open.

## Active Chunk

`WS-POL-001-01` is drafted for human review. Implementation has not started.

## Chunk Status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-POL-001-01` | Planning PR open | `codex/submission-artifact-policy-loop-plan` | 26 | Awaiting human approval before implementation. |
| `WS-POL-001-02` | Planned | - | - | Starts after policy foundation lands. |
| `WS-POL-001-03` | Planned | - | - | Moves submission creation to effective policy. |
| `WS-POL-001-04` | Planned | - | - | Splits post-submit checker policy provenance. |
| `WS-POL-001-05` | Planned | - | - | Proves revision resubmission and real API drill. |

## Blockers

| Blocker | Owner | Next action |
|---|---|---|
| Human approval of chunk sequence and first contract | User | Review PR #26. |
| Persisted policy provenance field names | User + Codex | Confirm during PR #26 review. |

## Follow-Ups

| Item | Source | Priority |
|---|---|---|
| Replace `evidence_policy`, `required_files`, and `required_evidence` with `SubmissionArtifactPolicy` path | Discovery | High |
| Split pre-submit and post-submit policy provenance fields | Discovery | High |
| Add revision resubmission pre-submit proof | Discovery | High |
