# Chunk Contract: WS-CI-001-02A — Safe Migrate-Once Database Reset

## Parent initiative

`WS-CI-001` — Backend CI Acceleration

## Goal

Adopt and repair Konan's migrate-once reset and fixture work under the existing
CI topology, proving destructive reset containment before lane orchestration.

## Immutable contributor source

- `e22e9fba681f6f076d67433c90a268218be7662b`
- `c73b28931b3b2a68a9ee2389181220132efaa41e`

Only reviewed changes from these commits and the exact allowlist below are
eligible. Later PR #180 commits are new discovery. The resulting implementation
commit and PR evidence must preserve Konan's authorship.

## Risk class

L1 / P0 CI integrity and destructive test-data handling

## SLA

P1

## Start phase

`implementation`

## Allowed files

- `backend/pyproject.toml`
- `backend/tests/conftest.py`
- `backend/tests/test_actors.py`
- `backend/tests/test_alembic.py`
- `backend/tests/test_api_rate_controls.py`
- `backend/tests/test_artifact_admission.py`
- `backend/tests/test_artifact_recovery.py`
- `backend/tests/test_audit.py`
- `backend/tests/test_auth.py`
- `backend/tests/test_authorization.py`
- `backend/tests/test_checkers.py`
- `backend/tests/test_database_reset.py`
- `backend/tests/test_outbox.py`
- `backend/tests/test_projects.py`
- `backend/tests/test_tasks.py`
- `.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/STATUS.md`
- `.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/reviews/WS-CI-001-02A-internal-review-evidence.md`
- `.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/reviews/WS-CI-001-02A-pr-trust-bundle.md`
- `.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/reviews/WS-CI-001-02A-external-review-response.md`
- `.agent-loop/merge-intents/WS-CI-001-02A.json`

## Not allowed changes

- workflow topology, lane/shard runners, coverage commands, product code,
  production migrations, API behavior, or service architecture;
- removed, skipped, deselected, or weakened tests or behavioral assertions;
- destructive reset against an admin, default, non-test, unexpected, or
  runner-unowned database/role;
- dynamic acceptance of unknown tables, duplicated guard inventories, or
  triggers left disabled on any exit path.

## Acceptance criteria

- [ ] The reset authenticates the expected runner-generated database name and
      least-privileged owner role before any trigger, truncate, or schema action
      and rejects admin/default/non-test/wrong-role targets.
- [ ] One canonical reset inventory defines resettable tables, protected
      migration state, and all seven trigger-guarded tables; implementation and
      tests import the same source and fail closed on unknown schema objects.
- [ ] Success, repeated reset, injected failure, transaction rollback, signal,
      wrong database, wrong role, admin URL, and unexpected-table tests prove no
      out-of-lane data is reset and no trigger remains disabled.
- [ ] Alembic state and immutable actor migration state remain byte-for-byte
      unchanged, and schema-owning migration tests rebuild safely.
- [ ] Every fixture-migrated module retains the same collected tests and no
      assertion is weakened; exact Boolean identity regressions are restored.
- [ ] Existing real PostgreSQL, MinIO, API, migration, lock, trigger,
      constraint, transaction, concurrency, coverage, and failure gates pass
      under the existing CI topology.
- [ ] Global 78% and every protected 90% coverage floor remain unchanged.

## Verification commands

```bash
cd backend
ci_verify_dir="$(mktemp -d)"
trap 'rm -rf -- "$ci_verify_dir"' EXIT
test -n "${WORKSTREAM_TEST_ADMIN_DATABASE_URL:-}"
ruff check app tests scripts
python -m pytest -q tests/test_isolated_database_runner.py
python scripts/run_isolated_tests.py --metadata-json "$ci_verify_dir/reset.json" --timeout-seconds 1200 -- python -m pytest -q tests/test_database_reset.py
python scripts/run_isolated_tests.py --metadata-json "$ci_verify_dir/collect.json" --timeout-seconds 12600 -- python -m pytest --collect-only -q
python scripts/run_isolated_tests.py --metadata-json "$ci_verify_dir/suite.json" --timeout-seconds 12600 -- coverage run -m pytest
coverage report --precision=2 --fail-under=78
coverage report --include='app/adapters/artifacts/*,app/core/cancellation.py,app/core/file_locks.py,app/interfaces/artifact_operations.py,app/interfaces/artifacts.py,app/modules/artifacts/*' --precision=2 --fail-under=90
coverage report --include='app/interfaces/external_services.py' --precision=2 --fail-under=90
coverage report --include='app/core/config.py' --precision=2 --fail-under=90
coverage report --include='app/workers/*' --precision=2 --fail-under=90
coverage report --include='app/main.py' --precision=2 --fail-under=90
coverage report --include='app/adapters/artifacts/s3_compatible.py' --precision=2 --fail-under=90
coverage report --include='app/core/s3_validation.py' --precision=2 --fail-under=90
coverage report --include='app/modules/audit/*' --precision=2 --fail-under=90
coverage report --include='app/modules/actors/*' --precision=2 --fail-under=90
coverage report --include='app/modules/authorization/*' --precision=2 --fail-under=90
coverage report --include='app/modules/api_controls/*,app/api/deps/api_controls.py' --precision=2 --fail-under=90
coverage report --include='app/modules/tasks/*' --precision=2 --fail-under=90
coverage report --include='app/interfaces/auth.py,app/core/auth.py,app/adapters/auth/dev.py,app/adapters/auth/flow.py' --precision=2 --fail-under=90
cd ..
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
git diff --check
```

## Required reviewers

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] CI integrity
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

Target ownership proof, protected/resettable inventory, rollback and trigger
restoration, test-delta equivalence, and contributor attribution.

## Stop conditions

Stop if signed implementation custody is absent, target ownership cannot be
proved, unknown schema state must be accepted, tests/coverage must be weakened,
or the existing CI topology cannot prove the reset safely.
