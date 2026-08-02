# External Review Response: WS-XINT-003-02B

## GitHub Actions round 1

Comments addressed:

- Backend docstring coverage failed at 79.7 percent because the new policy
  mutation surface added 22 undocumented callables. All new router,
  replay-repository, service, and validator callables now carry concise
  behavioral docstrings. The unchanged gate passes locally at 80.5 percent.

Comments deferred:

- None.

Human decisions needed:

- None. The gate and threshold were preserved.

Commands rerun:

- `cd backend && .venv/bin/ruff check app tests scripts`
- `cd backend && .venv/bin/docstr-coverage --config .docstr.yaml`

Remaining risks:

- GitHub Backend, Agent Gates, and CodeRabbit must pass on the replacement
  exact head before human merge.

## GitHub Actions round 2

Comments addressed:

- The semantic-lane inventory failed closed because the new
  `tests/test_project_policy_mutations.py` module had no canonical lane. It is
  now assigned to `shared_foundations` beside authorization and immutable policy
  lineage tests; no lane, threshold, or execution behavior changed.

Comments deferred:

- None.

Human decisions needed:

- None.

Commands rerun:

- The canonical collect-only runner passed the missing-lane check, then reached
  unrelated locally absent Pillow dependencies supplied by hosted CI.
- Focused CI lane-contract tests: 68 passed.

Remaining risks:

- Exact-head hosted checks and CodeRabbit remain required.

## CodeRabbit round 1

Comments addressed:

- Replay immutability now includes `created_at`, and downgrade locks all three
  custody tables before its emptiness decision.
- The historical-fixture custody helper admits only the two exact new
  review/revision table-trigger pairs.
- Project fixtures copy nested policy input before removing obsolete fields.
- Operator guidance gives the exact replacement selector construction.
- The custody lookup has a matching migration/ORM composite index.
- Replay disposition, route dependency tuples, and `_existing` are typed.
- Reservation mismatch, pending, and replayed service branches now have direct
  tests; the migration test distinguishes independent upgraded selectors from
  the coupled downgraded constraint.
- The smaller ordering comment, exact exception, repository/E2E docstrings,
  and argument documentation were also corrected.

Comments deferred:

- None.

Human decisions needed:

- None.

Commands rerun:

- Ruff: passed.
- Policy mutation and lane-contract tests: 81 passed.
- New-subsystem coverage: 13 passed, 92.86 percent.
- Migration `0047:0048` offline SQL generation: passed.
- Markdown links and whitespace: passed.

Remaining risks:

- PostgreSQL migration behavior and the full suite remain assigned to the
  replacement exact-head Backend run.

## GitHub Actions round 3

Comments addressed:

- All four lanes executed, then evidence validation reported interruption
  because database tests rejected the new replay ledger as an unexpected table.
  The canonical reset fingerprint now includes
  `policy_mutation_idempotency_records`, and its immutable truncate trigger is
  included in the exact guarded-table reset list.

Comments deferred:

- None.

Human decisions needed:

- None.

Commands rerun:

- Policy mutation and non-database reset checks passed locally. Database-backed
  reset proof remains on hosted CI because this worktree has no test database URL.

Remaining risks:

- Exact-head hosted evidence validation and full coverage remain required.
