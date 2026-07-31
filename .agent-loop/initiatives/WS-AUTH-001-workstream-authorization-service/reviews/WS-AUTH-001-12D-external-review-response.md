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
- GitHub full backend suite and coverage: required again on the corrected SHA.

## Remaining risks

- Hosted semantic lanes and coverage must pass on the next corrected exact head.
- CodeRabbit must re-review the corrected exact head with no unresolved findings.
