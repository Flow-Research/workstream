# PR Trust Bundle: WS-CON-001-03A

## Outcome

Adds a linear PostgreSQL/SQLAlchemy persistence foundation for project-scoped
compensation adapter bindings at migration `0053_compensation_bindings`.

## Design And Boundaries

- Stores project, instrument, canonical actor FK, non-secret route key,
  lifecycle version, and lifecycle provenance columns.
- Allows only active version-1 inserts with null suspension/retirement facts.
- Rejects every update until later authorized lifecycle chunks replace the
  guard.
- Enforces one active binding per project/instrument and exact route-key
  syntax in Pydantic and PostgreSQL.
- Stores no endpoint, credential, token, account, balance, or provider ref.
- Exposes no creation repository/service and adds no AUTH or adapter behavior.

## Reconciliation

The branch was refreshed after ART PR #264 advanced main and consumed migration
`0052_legacy_intake_removal`; this migration was reconciled as its linear 0053
child. The pre-existing user-owned PDF deletion remains excluded.

## Verification

- Focused PostgreSQL behavior: 18 passed.
- Migration downgrade/upgrade plus live schema: 1 passed.
- Focused compensation coverage: 100%.
- Single Alembic head, Ruff, Markdown links, stale wording/auth scans, and diff
  hygiene pass.
- All eight required internal reviewer tracks pass on exact implementation
  commit `684cad7c87a2ebac9e5ad91c8e2cdbabecd6235a`.

## Human Review Focus

1. Confirm 03A remains schema-only and active-only.
2. Confirm current ART/REV service identities are not treated as compensation
   adapter authority.
3. Confirm 04A remains blocked on an AUTH-approved adapter identity/capability.
4. Confirm no credential/provider material can enter the aggregate.

## Remaining External Gate

GitHub CI and CodeRabbit must pass on the published exact head. The next chunk
is `WS-CON-001-03B` and requires a separate explicit start.
