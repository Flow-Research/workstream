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

Worker cutover, approval behavior, checker execution, broad compilation
permission, synthetic human authority, compatibility path, or ART semantics.

## Acceptance

- One immutable current compilation per exact source/catalogue/setup generation.
- Strict validation and sanitization precede atomic persistence.
- Existing policy projections bind exact compilation/component hashes.
- Fresh fixed-service PREP is consumed per protected transaction; replay,
  copied/wrong handle, stale context, or partial failure creates no effect.
- Agent-derived projections cannot be updated in place.
- Compilation creation/supersession consumes the exact fixed-service execute
  action; PM recovery consumes the exact request action. Projection writes
  separately consume their 12E/12F/12G PREP and cannot borrow compilation
  authority.

## Verification and review

Postgres migration/constraint/concurrency/rollback tests plus AUTH all-pairs
denials and 90% changed-subsystem coverage. Required reviewers: all L1 tracks.
