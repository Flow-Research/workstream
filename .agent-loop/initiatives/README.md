# Initiative Records

These directories preserve planning, decisions, evidence, and review history.
They are not live instructions or an authorization system.

Older records may mention retired signed-start, loop-memory, machine-scope, or
recovery scripts. Those references describe the process used at that time; do
not execute them as current commands. Current contribution guidance lives in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md).

Current initiative disposition and remaining boundaries live in
[`CURRENT_STATE.md`](../CURRENT_STATE.md). Use GitHub's open pull requests for
transient work. Do not infer current work from a review file, branch name, old
`Active` field, or chronological log entry.

## Historical ENG Initiatives

ENG-001 through ENG-008 record the repository-control work that preceded the
simple engineering loop restored by PR #207. Their individual `STATUS.md` and
`CHUNK_MAP.md` files record exact merged, retired, and never-implemented
outcomes.

None of these initiatives has an active successor. In particular, historical
signed-start, loop-memory, recovery, machine-scope, mutation, property-testing,
and review-archive proposals do not authorize current work. A useful unfinished
idea must re-enter as a fresh bounded initiative against current repository
behavior.

| Initiative | Final disposition |
|---|---|
| [WS-ENG-001](WS-ENG-001-codex-zero-trust-loop-bootstrap/STATUS.md) | Complete; signed-loop runtime retired |
| [WS-ENG-002](WS-ENG-002-single-checkpoint-loop-start/STATUS.md) | Complete; signed-start runtime retired |
| [WS-ENG-003](WS-ENG-003-loop-memory-recovery/STATUS.md) | Complete; recovery runtime retired |
| [WS-ENG-004](WS-ENG-004-writer-directed-start/STATUS.md) | Complete; writer-directed signed starts retired |
| [WS-ENG-005](WS-ENG-005-parallel-initiative-execution/STATUS.md) | Complete; simple branch/worktree concurrency retained |
| [WS-ENG-006](WS-ENG-006-contributor-engineering-onboarding/STATUS.md) | Complete; simplified contributor entry retained |
| [WS-ENG-007](WS-ENG-007-concurrent-pr-review-reconciliation/STATUS.md) | Recovery complete; proposed successors superseded |
| [WS-ENG-008](WS-ENG-008-repository-native-sdlc-assurance/STATUS.md) | Partially merged, then intentionally superseded |
