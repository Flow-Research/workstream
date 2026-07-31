# WS-AUTH-001-12D External Review Response

## Comments addressed

- Major: preserve explicit `null` values in the guide-update idempotency digest
  while omitting unset fields, matching the actual update semantics. Added a
  regression proving explicit null and omission cannot replay under one key.
- Major: roll back failed activation transactions before restoring both
  test-only guide triggers in the downstream fixture and API E2E seed.
- Minor: distinguish ordinary authorization-decision transaction failures from
  prepared-authorization transaction failures in logs.
- Minor: document both triggers suspended by the isolated downstream seed and
  correct the source-snapshot broker-failure test wording.
- Test completeness: exercise both system-scoped and exact-project Project
  Manager grants for all three guide mutation actions.
- Reuse: remove the unreachable legacy snapshot/setup-run creation and dispatch
  helper chain from `ProjectService`.
- Hosted CI: update downstream task/checker construction to use required UUID
  idempotency and the clean-cut guide request, with lifecycle policies seeded
  independently as test prerequisites.
- Second hosted CI: preserve secret-looking durable-ref rejection in the shared
  manifest builder; use the canonical actor-profile ID in isolated activation
  seeds; install exact-project authority before revoking system authority; and
  replace stale legacy-manifest mutation expectations with database-immutability
  proof.
- Final internal review: reject suffixed `.npmrc`/`.pypirc` refs and thread the
  exact run-specific Flow subject and issuer through both API E2E activation
  seeds.
- Third hosted CI: construct pre-0045 ART guide-binding lineage only through an
  isolated-test, fixed-allowlist custody suspension and restore migration 0045
  before current ORM models are used after the extraction-migration downgrade.
- Fourth hosted CI: apply the same explicit historical-lineage boundary to the
  shared ART admission/recovery fixtures, seed the intentionally old 0028 schema
  without current-model columns, and update exact active-action/dependency
  assertions for the AUTH-12D cutover.
- Fresh CodeRabbit review: reuse the strict runner-owned trigger suspension in
  the downstream activation fixture, and require secret/token/credential name
  boundaries so benign words such as `secretary` are not over-blocked.
- Product re-review extended those word boundaries to guide durable refs, with
  benign source names admitted while the full credential/local-ref denial
  matrix remains fail-closed.
- Fifth hosted CI: distinguish lock-based lineage protection from the stronger
  immediate guide/item immutability guards, while preserving the post-lock
  stale-lineage assertion through the isolated historical fixture.

## Comments deferred

None.

## Human decisions needed

None. The user retains merge authority for PR #232.

## Commands rerun

- Ruff on all corrective files: passed.
- Isolated PostgreSQL correction lane covering downstream task/checker setup,
  explicit-null replay, and system/project grant paths: 9 passed.
- The exact second-run regression selection completed 36 tests without a failure
  before the intentionally stopped local run; the complete semantic lanes remain
  assigned to GitHub because local execution is prohibitively slow.
- Git diff check: passed.
- Focused isolated PostgreSQL historical guide-binding proof: 1 passed.
- Focused isolated PostgreSQL downgrade/restore extraction proof: 1 passed.
- Exact stale-generation, next-generation, and post-read drift regressions:
  3 passed in a runner-owned isolated PostgreSQL database.
- Representative ART guide admission, checker, 0028 migration, and recovery
  regressions: 4 passed in a runner-owned isolated PostgreSQL database.
- Active-action and dependency allowlist assertions: 2 passed.
- Exact guide-lineage lock/immutability regression: 1 passed.
- Guide-source credential/local-ref denial matrix: 46 passed; benign
  secretary/tokenizer/credentialing source refs: 3 passed.
- GitHub full backend suite and coverage: required again on the corrected SHA.

## Remaining risks

- Hosted semantic lanes and coverage must pass on the next corrected exact head.
- CodeRabbit must re-review the corrected exact head with no unresolved findings.
