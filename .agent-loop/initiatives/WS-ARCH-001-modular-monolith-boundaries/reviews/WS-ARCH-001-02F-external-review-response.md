# WS-ARCH-001-02F External Review Response

## Comments addressed

- Added every changed planning, state, and PostgreSQL proof file to the chunk's
  allowed mutation scope.
- Restricted every new Alembic metadata assertion to the `public` schema.
- Preserved the canonical physical check-constraint name with `op.f(...)`;
  hosted schema-contract tests prove it matches the ORM convention.
- Configured the PostgreSQL rollback proof without leaving an implicit
  transaction open before the transaction-owning command.

## Comments deferred

None.

## Human decisions needed

None.

## Commands rerun

- Ruff on the changed migration and tests.
- Focused TASK, architecture, and behavior-ownership tests.
- GitHub Backend semantic lanes and Agent Gates on the exact PR head.

## Remaining risks

None identified from the CodeRabbit review threads.
