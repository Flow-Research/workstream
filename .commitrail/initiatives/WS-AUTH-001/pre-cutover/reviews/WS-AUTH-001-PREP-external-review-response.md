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
- CodeRabbit run `d64c773b-4f76-491e-ae6e-cab19d25dc4b` correctly found that
  the trust bundle did not bind its external-check statements to the exact
  published SHA. The bundle now names head
  `8a705e5bb104fb77d3a589f37b1eb45987b2515d`, passing Agent Gates run
  `29784118660`, the CodeRabbit run, and then-pending sharded Backend run
  `29784025021` separately.
- Sharded Backend run `29784025021` completed with shard 2 failing in the eight
  PREP/real-lifecycle race cases. Focused PostgreSQL reproduction identified
  fixture-only defects: two synthetic grants were marked as bootstrap grants,
  audit assertions used legacy column/event names, teardown did not restore the
  bootstrap control singleton, and mutation-first assertions expected detailed
  lifecycle disclosure instead of the kernel's fail-closed
  `permission_not_granted` result. The fixture now establishes one valid
  bootstrap administrator, attributes the target grant to it, restores control
  state during teardown, and asserts the canonical privacy-safe audit contract.

## Comments Deferred

None.

## Human Decisions Needed

None for the repair. Human merge approval remains required after hosted checks
pass.

## Commands Rerun

- `python -m ruff check tests/test_authorization.py`
- `python -m pytest -q tests/test_authorization.py -k 'prepared_ and not
  postgresql and not crossed_mutations and not crosses_real'` (`18 passed`)
- isolated PostgreSQL `pytest -q tests/test_authorization.py -k
  'prepared_postgresql or prepared_actor_authority_crossed_mutations or
  prepared_crosses_real_lifecycle_service_transactions'` (`13 passed`)

The full-suite coverage proof remains assigned to GitHub Backend rather than
the slow local machine.

## Remaining Risks

Full repository coverage must pass on the refreshed published SHA. This repair
creates a descendant SHA, so CodeRabbit and all required GitHub checks must also
complete before merge readiness.
