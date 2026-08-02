# External Review Response: WS-XINT-002-04B

## Runtime comments addressed

- The custody table now labels every action row as Active or Planned.
- Review evidence now states that local review is provisional until hosted
  database-backed full coverage passes on the exact PR head.
- Guide materialization preserves its bounded public error when best-effort
  incident persistence fails, and format-inspection deadline failures use the
  same bounded incident path.
- Concurrent guide reads no longer take an exclusive lock on the immutable
  singleton storage-namespace row. Exact mutable lineage remains locked through
  provider access and the protected write.
- The lock-contention test now proves PostgreSQL SQLSTATE `55P03` directly
  instead of accepting any `DBAPIError` as evidence of a lock.
- Fixed-service context construction now verifies that the loaded profile has
  the exact requested service identity.
- Guide PREP scope composition is action-gated through one module-level map.
- Inert test parameters and the unused materialization-helper authority were
  removed. The dataclass binding request is updated with `dataclasses.replace`.
- The hosted active-action audit expectation now includes both 04B actions.

## Runtime comment rejected as stale

- The claimed authority-fact mismatch does not exist on this branch.
  `GuideSourceBindingAuthorityFacts` already contains `logical_role`, and
  `GuideSourceReadAuthorityFacts` already contains `binding_id`; focused tests
  construct and consume both strict resource contexts.

## Runtime comment deferred

- A new database `lock_timeout`/`statement_timeout` and lock-duration metric are
  not added in 04B. The provider operation already runs under the bounded
  `ArtifactPreparationService` deadline. PostgreSQL `statement_timeout` does
  not bound time spent awaiting provider I/O after the locking statement has
  completed, while an observability surface is outside this activation chunk.
  ART worker operational tuning can add a transaction-idle bound and metric in
  a dedicated, evidence-backed chunk without weakening the required lineage
  lock.

## Earlier planning comments addressed

- The verification command no longer uses a shell-redirection-shaped
  `<test-db>` placeholder; it consumes `WORKSTREAM_TEST_DATABASE_URL`.
- Background executor wording uses the exact terms `Celery task payload` and
  `Celery task/route composition`.

## Verification

- Corrective implementation commit
  `d3917e0b4cf30cba5b840cce2d76de39fd09ae68` and exact local commands are
  recorded in the internal review. Hosted-run identifiers remain pending the
  evidence-only follow-up commit and exact-head GitHub run.
- Local Ruff, focused AUTH/audit/architecture tests, stale authorization docs,
  stale artifact contracts, Markdown links, and `git diff --check` pass.
- Database-backed guide tests and repository-wide coverage remain assigned to
  hosted `Backend / test` because this shell has no
  `WORKSTREAM_TEST_DATABASE_URL`.

## Remaining risk

PR #245 remains non-merge-ready until CodeRabbit threads are resolved and
hosted exact-head `Backend / test` plus `Agent Gates / agent-gates` pass.
