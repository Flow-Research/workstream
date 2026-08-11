# Discovery

Discovery was performed on `main` at merge commit `98eae13e`.

## Current persistence surface

- `backend/alembic/versions/` contains 63 linear revisions from
  `0001_initial_baseline` through `0063_compilation_authority`.
- Those revisions contain about 18,004 lines and 639 raw/schema construction or
  seed operations.
- `Base.metadata` currently exposes 74 ORM tables.
- The chain installs behavior that metadata creation alone cannot reproduce:
  PostgreSQL functions and triggers, append-only and immutable guards, partial
  and expression indexes, closed enum/check values, catalogue evidence rows,
  service identities, and canonical reference state.
- Migration-specific tests occupy about 14,440 lines across
  `backend/tests/test_alembic.py` and focused `test_migration_contract.py`
  modules. Ninety test functions primarily prove historical transitions and
  downgrade refusal.

## Runtime and tooling dependencies

- `backend/alembic/env.py` binds migrations to the complete application
  metadata.
- `backend/scripts/run_isolated_tests.py` upgrades every isolated database to
  head and records the head in custody evidence.
- The semantic schema lanes partition `tests/test_alembic.py`; the historical
  chain is the dominant hosted schema-lane cost.
- Current API drills and fixtures assume a clean database can reach head before
  application tests begin.
- `backend/migration_contracts/service_identity_0023.py`,
  `app.modules.actors.service_identity_migration`, and
  `scripts/service_actor_identity_mapping.py` exist solely to upgrade legacy
  service profiles through revision 0023. They are obsolete in a clean-cut
  baseline and must not remain imported by runtime code.

## Required preservation

The reset must preserve the final state, not the historical construction path:

1. all tables, columns, generated/default expressions, primary/foreign/unique
   keys, checks, indexes, sequences, types, functions, and triggers;
2. exact authorization permission/action evidence and fixed-service registry
   rows required by current runtime catalogues;
3. database mutation guards and append-only enforcement;
4. schema/model/catalogue parity and clean isolated-test provisioning;
5. one exact Alembic head recorded in hosted evidence.

## Documentation classification

Historical initiative contracts and review logs may retain old revision names
as history. Current operations/specification pages, executable tests, fixtures,
and scripts must reference only the new baseline and must not instruct users to
upgrade through the removed chain.

## Principal risk

Autogeneration from SQLAlchemy metadata is insufficient. The new baseline must
be derived from and compared with a clean database produced by the trusted old
head, including non-table objects and canonical seed rows, before the old chain
is removed.
