# External Review Response: WS-ART-001-03B3A

## Comments addressed

- Made cancellation evidence persistence resistant to repeated cancellation and
  bounded by a five-second timeout while preserving cancellation as the caller
  result.
- Made concurrent extracted-content publication deterministic with PostgreSQL
  `ON CONFLICT DO NOTHING`, locked reload, and exact-output comparison.
- Added durable TTL-bearing extraction-workspace custody to the canonical
  scratch ledger and stale crash cleanup before ownership release.
- Added a real outside-scratch write denial probe.
- Normalized relative imports in the extraction architecture boundary test.
- Repaired hosted database tests that inserted dependent extraction rows before
  their classification was flushed and invoked synchronous Alembic from an
  active event loop.

## Comments deferred

- The suggestion to add compat and x32 ABIs to the libseccomp allow-list was not
  adopted. The native-only libseccomp filter rejects an architecture mismatch;
  adding alternate architectures would expand the accepted syscall surface.
  Failure to install or load the native filter remains
  `isolation_unavailable`.

## Human decisions needed

None.

## Commands rerun

- `ruff format` and `ruff check` on every repair file.
- Focused extraction isolation, workspace lifecycle, stale cleanup, and
  architecture tests: 6 passed.
- The first hosted repaired Backend run exposed six database-test defects after
  1,751 passing tests; those test defects are repaired and require the next
  hosted run.

## Remaining risks

The full PostgreSQL and repository coverage proof remains delegated to the
hosted Backend gate. No CI threshold or test assertion was weakened.
