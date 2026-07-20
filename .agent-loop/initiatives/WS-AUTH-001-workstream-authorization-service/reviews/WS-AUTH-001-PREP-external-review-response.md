# WS-AUTH-001-PREP External Review Response

## Comments Addressed

- GitHub Backend run `29759124278` failed in the full-suite coverage step. The
  thirteen direct failures came from the new PostgreSQL tests: fixture setup
  attempted bootstrap-provenance grants after bootstrap completion, and fixture
  teardown attempted to delete immutable identity history with user triggers
  enabled. The first teardown rollback left authorization evidence behind,
  causing 344 downstream migration-setup errors and the derivative coverage
  failure.
- Fixture-only setup and teardown now disable the relevant PostgreSQL user
  triggers for test data insertion/deletion and re-enable them before commit.
  Database indexes and constraints remain active, so the duplicate active
  same-role grant case still proves rejection through the canonical unique
  index.

## Comments Deferred

None.

## Human Decisions Needed

None for the repair. Human merge approval remains required after hosted checks
pass.

## Commands Rerun

- `python -m ruff check tests/test_authorization.py`
- `python -m pytest -q tests/test_authorization.py -k 'prepared_ and not
  postgresql and not crossed_mutations and not crosses_real'` (`18 passed`)

The PostgreSQL/full-suite repair proof remains assigned to GitHub Backend rather
than the slow local machine.

## Remaining Risks

The repaired PostgreSQL cases and full repository coverage must pass on the
next GitHub Backend run. Agent Gates passed, and CodeRabbit completed without
comments on the prior published SHA.
