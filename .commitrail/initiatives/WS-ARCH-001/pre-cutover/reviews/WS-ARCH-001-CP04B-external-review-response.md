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
- CodeRabbit's seven final-head findings were replayed and accepted. The CP04B
  contract sentence and criterion map are now exact; migration `0007` uses the
  physical check-constraint names produced by the ORM naming convention;
  publish/retire validate their required owner ports before duplicate recovery;
  AUTH digest parity is derived independently from seeded server facts; opaque
  authority lifecycle assertions prove the prepared handle is consumed and
  closed exactly once; PostgreSQL concurrency helpers clean up on every failure;
  and the caller-fact structural test now has an accurate name.

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
- Ruff passed across the complete CONTRIBUTIONS module and test package.
- The non-PostgreSQL focused CodeRabbit regression set passed: 36 tests.
- The five PostgreSQL concurrency tests remain hosted-only because local
  execution requires `WORKSTREAM_TEST_DATABASE_URL`; GitHub CI owns that proof.
- The first corrective hosted replay correctly rejected the old public-schema
  fingerprint after migration `0007` adopted the ORM's physical constraint
  names. The pinned fingerprint now records the resulting canonical schema;
  no schema check or threshold was weakened.
- Adopted test-delta review rejected the fake-repository rollback assertion as
  incompatible transaction custody. CP04B now proves the publication-specific
  boundary with real PostgreSQL: authority evidence is staged, custody and the
  lifecycle event reach PostgreSQL, a late event-flush failure is injected, and
  rollback leaves the policy/version draft, with no custody, publication event,
  or staged authorization effect.
- QA's discriminating probe then proved the first PostgreSQL replacement could
  still pass if failure occurred before event flush. The late-failure repository
  now asserts, inside the open transaction, that the policy/version transition,
  custody, lifecycle event, and staged AUTH evidence are all visible before it
  injects failure. A pre-flush failure therefore cannot satisfy the test.

## Remaining risks

- Hosted PostgreSQL and complete-suite evidence must be replayed on the final
  corrective head before merge readiness is claimed.
