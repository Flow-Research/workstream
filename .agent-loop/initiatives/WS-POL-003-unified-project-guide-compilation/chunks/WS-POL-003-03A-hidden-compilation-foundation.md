# Chunk Contract: WS-POL-003-03A - Hidden Compilation Foundation

Status: Proposed after 02; inactive. Risk: L1.

## Goal

Add immutable attempt/compilation persistence, trusted validation, append-only
supersession, and deny-by-default request/execute seams without making a model
call or a live product mutation.

## Allowed files

Project compilation models, schemas, validator, repository, composition seam,
one then-current Alembic migration, focused tests, and WS-POL-003 docs.

## Not allowed

Action activation, provider calls, Celery cutover, policy projections,
approval, checker execution, compatibility paths, or ART changes.

## Acceptance

- One durable attempt is uniquely bound to canonical input hash, project,
  guide/source, both catalogue snapshots, setup run/generation, agent identity,
  and instruction version; compare-and-swap selects one current compilation.
- States distinguish reserved, provider-uncertain, accepted, invalid-terminal,
  persisted, and superseded. Invalid/unsafe output terminally consumes the
  generation; transport uncertainty alone is reconciled under the same key.
- Reservation commits before provider I/O. No transaction/lock spans I/O.
- Strict validation, safe text, evidence grammar, component hashes, and
  append-only invariants are proven while every runtime seam denies.

## Verification and review

PostgreSQL migration/uniqueness/CAS/crash-state tests, validator/security tests,
Ruff, hosted CI, and all L1 reviewer tracks. Human focus: durable cardinality
and fail-closed hidden state.
