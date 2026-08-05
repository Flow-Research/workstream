# Chunk Contract: WS-POL-003-03 - Compilation Persistence and Validator

Status: Proposed after 02 and required AUTH dependencies. Risk: L1.

Hard gate: the exact XINT/AUTH registration and activation for
`project.guide_compilation.request` and
`project.guide_compilation.execute` is merged. Generic fixed-service authority
or 12E/12F/12G projection authority cannot substitute for it.

## Goal

Add immutable compilation provenance, trusted validation, component hashes,
append-only supersession, and action-specific fixed-service mutation custody.

## Allowed files

Project models/schemas/repository/validator/composition, AUTH prepared-resource
composition only where exact existing actions require it, one then-current
Alembic migration, focused tests, and WS-POL-003/AUTH specification docs.

## Not allowed

Celery call-graph cutover, approval behavior, checker execution, broad compilation
permission, synthetic human authority, compatibility path, or ART semantics.

## Acceptance

- A database `UNIQUE` constraint covers exact `project_id`, `guide_id`, source
  snapshot ID, pre- and post-catalogue snapshot hashes, setup run ID, and setup
  generation. The setup-run current-compilation pointer advances only by
  compare-and-swap against its locked expected generation/current ID. Concurrent
  requests therefore converge on one immutable compilation rather than two
  current rows.
- Strict validation and sanitization precede atomic persistence.
- Existing policy projections bind exact compilation/component hashes.
- Fresh action-specific fixed-service PREPs are prepared separately, but all
  required handles are consumed in the single root database transaction that
  owns compilation, projection links, and authorization evidence. Replay,
  copied/wrong handle, stale context, or any partial failure rolls back the
  whole unit and creates no durable effect.
- Agent-derived projections cannot be updated in place.
- Compilation creation/supersession consumes the exact fixed-service execute
  action; PM recovery consumes the exact request action. Projection writes each
  consume their separate 12E/12F/12G PREP in that same root transaction and
  cannot borrow compilation authority.

## Verification and review

Postgres unique-key, compare-and-swap, concurrent-insert, PREP atomicity, and
rollback tests plus AUTH all-pairs denials and 90% changed-subsystem coverage.
Required reviewers: all L1 tracks.
