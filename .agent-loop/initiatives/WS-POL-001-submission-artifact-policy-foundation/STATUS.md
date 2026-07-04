# Status: WS-POL-001 - Submission Artifact Policy Foundation

## Current Status

`WS-POL-001-01`, `WS-POL-001-02`, `WS-POL-001-03`, and `WS-POL-001-04` are
merged to `main`. `WS-POL-001-03` merged through PR #63 on 2026-07-03 after
internal review, CodeRabbit, and GitHub Actions completed. `WS-POL-001-04`
merged through PR #65 after deterministic verification, internal reviewer
fanout, CodeRabbit, GitHub Actions, and user merge approval.

`WS-POL-001-04` owns post-submit checker policy provenance. `WS-POL-001-05` has
implemented revision resubmission, the real API drill, and the
`evaluation_pending` post-submission lifecycle status correction. Deterministic
proof, internal reviewer repair, evidence, and trust bundle are complete.
GitHub checks are passing on PR #66. CodeRabbit detailed review is rate-limited
on the latest head, so the PR is awaiting user PR review or a later CodeRabbit
retry.

## Active Chunk

`WS-POL-001-05` - Revision Resubmission And Real API Drill

## Chunk Status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-POL-001-01` | Merged | `codex/ws-pol-001-01-submission-artifact-policy` | 28 | Implements guide-source snapshots, guide sufficiency reports, submission artifact policy, effective project policy, project pre-submit checker contract, activation guards, and key-based artifact policy merge. |
| `WS-POL-001-02` | Merged | `codex/ws-pol-001-02-agent-runtime-compiler` | 61 | Adds async guide sufficiency / derivation agents, runtime port, OpenAI Agents SDK adapter boundary, trusted compiler path, and server-owned provenance guards. |
| `WS-POL-001-03` | Merged | `codex/ws-pol-001-03-task-locked-context` | 63 | Moves task locked-context and submission runtime to the effective policy and project checker bundle. |
| `WS-POL-001-04` | Merged | `codex/ws-pol-001-04-post-submit-policy` | 65 | Splits post-submit checker policy provenance and locks durable checker runs to post-submit policy context. |
| `WS-POL-001-05` | Awaiting user PR review | `codex/ws-pol-001-05-revision-resubmission` | 66 | Proves revision resubmission, real API drill, and `evaluation_pending` lifecycle status. GitHub checks passed; CodeRabbit detailed review is rate-limited. Reviewed SHA: `5019afc57e7c6f5f7488f26a05b11c65a33e9f18`. |

## Blockers

| Blocker | Owner | Next action |
|---|---|---|
| None | - | Human review and explicit merge decision for PR #66. |

## Follow-Ups

| Item | Source | Priority |
|---|---|---|
| Add public revision lifecycle coverage instead of direct `needs_revision` test setup | Test-delta review | High for `WS-POL-001-05` |
| Add focused `0007 -> 0006` downgrade assertion for locked-context columns and constraints | QA/test-delta review | Medium follow-up |
| Extract shared artifact path and forbidden-pattern helpers before further checker-policy expansion | Reuse/dedup review | Medium follow-up |
