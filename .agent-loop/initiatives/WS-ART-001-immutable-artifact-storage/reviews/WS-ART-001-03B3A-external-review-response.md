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
- Rebased onto merged AUTH-12A and moved guide extraction to Alembic revision
  `0042_guide_extraction`, preserving the AUTH project-mutation evidence head.
- Made successful replay selection deterministic and replaced duplicated policy
  literals with the canonical extraction-policy constant.
- Moved extraction workspace ownership behind a public
  `ArtifactScratchManager` context manager, made cleanup recursively bounded and
  descriptor-relative, and made every ledger mutation preserve explicit
  workspace custody without hidden write-time backfill.
- Added nested parser-residue cleanup coverage and made request fixtures use
  explicit lineage fields.
- Scoped successful replay to the current extraction policy on both the attempt
  and canonical content, with PostgreSQL regression coverage for obsolete-policy
  success evidence.
- Prevented a second materialization slot from being claimed unless a current-
  policy `parser_failure` or `cancelled` attempt durably proves retry authority.
- Serialized the remaining retry slot with a PostgreSQL row lock and added a
  concurrent-claim regression proving exactly one request receives slot two.

## Comments deferred

- The suggestion to add compat and x32 ABIs to the libseccomp allow-list was not
  adopted. The native-only libseccomp filter rejects an architecture mismatch;
  adding alternate architectures would expand the accepted syscall surface.
  Failure to install or load the native filter remains
  `isolation_unavailable`.
- The suggestion to return successful extracted content when workspace cleanup
  fails was not adopted. An uncertain cleanup result is a scratch-custody
  failure, so the operation remains fail closed while the workspace stays in
  the manager-owned pending-cleanup set.

## Human decisions needed

None.

## Commands rerun

- `ruff format` and `ruff check` on every repair file.
- Focused extraction isolation, workspace lifecycle, stale cleanup, and
  architecture tests: 6 passed.
- After rebasing onto `64dd9c98`, changed-file Ruff format/check, Alembic
  single-head inspection, diff integrity, Markdown links, and stale-wording
  checks pass. The earlier 37-test focused run passed before the rebase repair;
  the refreshed PostgreSQL and focused proof is delegated to hosted CI because
  this worktree's incomplete local test environment resolves a conflicting
  global pytest plugin. Hosted checks must be refreshed on the new exact PR
  head.

## Remaining risks

The full PostgreSQL, schema-fingerprint, and repository coverage proof remains
delegated to the hosted Backend gate. No CI threshold or test assertion was
weakened.
