# WS-ENG-002-01 PR Trust Bundle

## Chunk and goal

`WS-ENG-002-01` makes the user's explicit start instruction a single operational checkpoint: the allowlisted orchestrator performs one authenticated GitHub dispatch and signed loop memory records it without a second approval.

## Human-approved intent

The user explicitly instructed the orchestrator to fix the redundant approval before other work. Merge remains human-owned.

## Changes and design

- Ordinary starts bypass the protected environment but require the dispatcher in a closed allowlist reviewed on trusted `main`.
- Start evidence has a versioned `github_workflow_dispatch` authorization envelope bound to the dispatcher.
- Historical two-person authority records remain valid without reinterpretation.
- Cancellation retains distinct protected-environment approval and does not depend on start-policy health.
- Exact-main, successor, prior-tip, replay, signing, serialization, and fixed-branch publication protections remain.

## Scope and product behavior

No backend/frontend runtime, API, database, dependency, Workstream product lifecycle, automated start, merge authority, or signing-key change.

## Proof, test delta, and CI integrity

- 75 focused tests and 88 agent-gate regression tests pass on the integrated head.
- Independent updater/checker branch coverage is 90.41/90.86 percent.
- Link, stale wording, stale authorization, stale artifact, compilation, and diff checks pass.
- Tests are additive; no CI permission, required check, or threshold was weakened.

## Reviewer results

All nine tracks pass integrated reviewed code SHA `2421751c`: senior, QA, security, product/ops, architecture, CI integrity, docs, reuse/dedup, and test delta.

## Remaining risks and external review

Changing the allowlist requires a normal reviewed PR. The existing `loop-memory-start` environment name now describes cancellation protection only; retaining it avoids an unrelated environment migration. Current main/ART was integrated without conflict or scope drift. Hosted CI and a fresh CodeRabbit review remain.

## Human review focus

Review the trusted-main actor allowlist, cancellation-only environment gate, dual-era event validation, and preservation of exact-main/successor/signature controls.

## Follow-up and human merge ownership

No successor chunk is declared. Only the user may approve and merge this PR.
