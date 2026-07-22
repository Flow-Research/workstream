# External Review Response

## Chunk

`WS-CI-001-02A` — Safe Migrate-Once Database Reset

## Source

GitHub Backend run `29924806229` on PR #186.

## Comments Addressed

- Shards 1, 3, and 4 exposed order-dependent schema contamination after
  whole-schema Alembic tests. Later ordinary tests correctly failed closed on
  missing final tables or a noncanonical fingerprint.
- The schema-contract fixture teardown previously trusted `upgrade head`, which
  cannot repair structural state when revision metadata already claims head.
- Setup and teardown for explicitly marked `postgres_schema_contract` tests now
  perform the same database-custody-checked drop, recreate, and migrate-to-head
  sequence under the database-specific DDL lock.
- A second hosted rerun exposed four migration-mutating tests outside
  `test_alembic.py`. The three artifact-admission migration tests and one task
  downgrade test are now individually marked as schema-contract owners, so
  they receive the same full rebuild without slowing their entire modules.
- Every unmarked database test now revalidates database custody and the full
  canonical schema fingerprint during teardown. The AST ownership scan remains
  early guidance; runtime verification is authoritative even when DDL is hidden
  behind aliases, helpers, fixtures, or another migration entry point.
- Ordinary resets retain the exact table inventory and full fingerprint gate.
- Removed the trust bundle's extra blank line at EOF.
- Removed CodeRabbit's valid obsolete `include_canonical_actors` reset argument;
  it had no callers and no behavior beyond deleting its value.

## Comments Deferred

- CodeRabbit's generic 80 percent docstring-coverage warning is not a repository
  gate and would require unrelated documentation churn outside signed 02A scope.

## Human Decisions Needed

None before rerunning CI. Merge still requires explicit user approval for this
specific PR.

## Commands Rerun

```bash
cd backend
ruff check tests/conftest.py tests/test_database_reset.py
python scripts/run_isolated_tests.py --metadata-json <temp>/repair.json \
  --timeout-seconds 1200 -- python -m pytest -q \
  tests/test_alembic.py::test_artifact_recovery_schema_and_empty_downgrade \
  tests/test_database_reset.py::test_database_reset_preserves_schema_and_restores_guards
cd ..
git diff --check
```

The focused ordering proof passed 2/2. Full-suite duration and coverage are
accepted only from the rerun GitHub Backend workflow.

The runtime-boundary proof also passed 2/2: direct Alembic ownership guidance
and hidden helper-driven schema drift rejected by ordinary fixture teardown.

## Remaining Risks

- All four hosted shards must prove that schema-contract tests no longer poison
  subsequent ordinary tests.
- Combined global 78 percent and every protected 90 percent coverage gate must
  pass unchanged.
