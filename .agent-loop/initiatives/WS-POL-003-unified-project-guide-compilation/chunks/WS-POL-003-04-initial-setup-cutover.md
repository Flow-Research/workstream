# Chunk Contract: WS-POL-003-04 - Initial Setup Pipeline Cutover

Status: Proposed after 03. Risk: L1.

## Goal

Replace the separate sufficiency and submission-policy inference calls with one
unified compilation, while producing the existing canonical report and draft
policy projections.

## Allowed files

Project setup worker/service/queue/composition, unified compilation services,
focused project/authorization/ART-boundary tests, and WS-POL-003 docs.

## Not allowed

Post-submit continuation cutover, approval semantics, checker execution,
serialized handles/material, or fallback to legacy guide excerpts.

## Acceptance

- Automatic and manual recovery converge on one deterministic setup run/task.
- Each generation persists one model-attempt row and provider idempotency key
  derived from the exact setup run/generation and compilation input identity.
  Dispatch and recovery atomically claim that row; retries use the same key.
- Provider acceptance must be recoverable by idempotent replay/result lookup,
  and the accepted result is persisted before downstream continuation. A
  timeout-after-acceptance retry reuses that result without another invocation.
- Invalid or unsafe output terminally consumes the generation's attempt;
  another evaluation requires a new setup generation.
- Blocked output creates no policy projection.
- Ready output atomically links sufficiency and draft artifact policy to one
  compilation.
- Stale/revoked/wrong-service/output failures occur before protected mutation.

## Verification and review

Celery concurrent-claim, retry/replay, timeout-after-acceptance, accepted-result
reuse, terminal-invalid-output, stale-generation, provider-failure, and rollback
tests plus hosted full coverage. Required reviewers: all L1 tracks.
