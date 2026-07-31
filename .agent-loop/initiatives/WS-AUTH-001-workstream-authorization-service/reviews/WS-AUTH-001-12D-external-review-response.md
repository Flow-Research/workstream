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

## Comments deferred

None.

## Human decisions needed

None. The user retains merge authority for PR #232.

## Commands rerun

- Ruff on all corrective files: passed.
- Isolated PostgreSQL correction lane covering downstream task/checker setup,
  explicit-null replay, and system/project grant paths: 9 passed.
- Git diff check: passed.
- GitHub full backend suite and coverage: required again on the corrected SHA.

## Remaining risks

- Hosted semantic lanes and coverage must pass on the corrected exact head.
- CodeRabbit must re-review the corrected exact head with no unresolved findings.
