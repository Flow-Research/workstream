# WS-ARCH-001-CP04B External Review Response

## Comments addressed

- GitHub shared-foundation lanes exposed existing contribution tests that still
  published by direct row mutation. Their helper now crosses the canonical
  hidden publication service, so the database custody guard remains strict.
- Existing model-column parity now includes the two transition-operation
  anchors installed by migration `0007`.
- The CP04A structure check no longer treats CP04A's intentionally superseded
  no-publish/no-retire assertions as permanent current-head behavior. CP04B's
  downstream negative-boundary tests remain active.

## Comments deferred

- None.

## Human decisions needed

- None beyond normal approval and merge authority.

## Commands rerun

- Ruff on the three affected test surfaces.
- CP04A structure and CP04B negative-scope tests: 17 passed.
- Five focused publication, retirement, active-policy race, and transaction-lock
  PostgreSQL regressions through the isolated migrated runner: 5 passed.
- Two incomplete-graph service regressions now assert the canonical concealed
  policy conflict rather than a later database error: 2 passed.
- The first hosted replay exposed one remaining legacy assertion that expected
  the forbidden active-policy/draft-version transition to fail only at commit.
  Migration `0007` correctly rejects that transition during the `UPDATE`, so
  the assertion now covers the complete database operation. The exact test
  passed against a freshly migrated isolated PostgreSQL database. Hosted lanes
  are replaying on the resulting head.
- The next hosted replay exposed the same retired direct-publication fixture in
  the ReviewLease persistence suite. That fixture now publishes its complete
  policy through the canonical hidden CONTRIBUTIONS service. All 8 ReviewLease
  persistence tests passed against a freshly migrated isolated PostgreSQL
  database; no REV behavior or production boundary changed.

## Remaining risks

- CodeRabbit has not produced a substantive review; its current result is a
  manual-review notice and must not be represented as approval.
