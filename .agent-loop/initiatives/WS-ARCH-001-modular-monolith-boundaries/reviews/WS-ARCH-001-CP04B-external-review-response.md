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
- Hosted exact-head lanes will be replayed after this correction is pushed.

## Remaining risks

- CodeRabbit has not produced a substantive review; its current result is a
  manual-review notice and must not be represented as approval.
