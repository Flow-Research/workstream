# WS-DB-001: v0.1 Schema Baseline Reset

## Human goal

Replace the accumulated development-only Alembic history with one canonical
v0.1 baseline before additional product migrations are added. Workstream does
not preserve or support upgrades from any pre-baseline development database.

## Success state

- `alembic upgrade head` on an empty PostgreSQL database installs the exact
  current schema, database enforcement, and canonical reference rows.
- Alembic exposes one revision and one head.
- The 63 historical revision files and tests of obsolete intermediate states
  are removed.
- Current ORM, runtime catalogue, fixed-service identity, trigger, constraint,
  index, enum, function, and seed-state contracts remain exact.
- All backend tests, the 78-percent repository floor, and protected 90-percent
  subsystem floors pass in hosted CI.

## Non-goals

- No data migration or compatibility bridge for existing development databases.
- No production behavior, permission, action, role, lifecycle, or API change.
- No schema redesign, table renaming, model cleanup, or new product capability.
- No weakening of immutable-data guards, downgrade guards, CI, or coverage.

## Human decisions already supplied

The repository is still building v0.1. Old development databases may be
discarded and recreated. Backward compatibility is explicitly not required.
