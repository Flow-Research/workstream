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
- Exactly one model invocation occurs per successful generation.
- Blocked output creates no policy projection.
- Ready output atomically links sufficiency and draft artifact policy to one
  compilation.
- Stale/revoked/wrong-service/output failures occur before protected mutation.

## Verification and review

Celery retry/replay/stale-generation/provider-failure/rollback tests and hosted
full coverage. Required reviewers: all L1 tracks.
