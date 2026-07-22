# Chunk Contract: WS-CI-001-02B — Exact-Custody Semantic Test Lanes

## Parent initiative

`WS-CI-001` — Backend CI Acceleration

## Goal

Replace arbitrary shards with dependency-based lanes after 02A proves the
migrate-once reset, while preserving exact execution and coverage custody.

## Preconditions

02A is merged with hosted reset evidence. This contract then requires its own
signed implementation start. Eligible contributor source is limited to commits
`e22e9fba681f6f076d67433c90a268218be7662b` and
`c73b28931b3b2a68a9ee2389181220132efaa41e`; later commits require review.

## Risk class

L1 / P0 CI integrity

## Start phase

`implementation`

## Allowed files

- `.github/workflows/backend.yml`
- `backend/scripts/ci_test_shards.py` (deletion only)
- `backend/scripts/run_isolated_tests.py`
- `backend/scripts/run_test_lanes.py`
- `backend/scripts/validate_test_lane_evidence.py`
- `backend/tests/test_ci_test_shards.py` (deletion only)
- `backend/tests/test_ci_test_lanes.py`
- `backend/tests/test_isolated_database_runner.py`
- `backend/tests/test_test_lane_evidence.py`
- `docs/operations_backend_testing.md`
- `scripts/test_agent_gates.py`
- this initiative's status, review, and evidence files
- `.agent-loop/merge-intents/WS-CI-001-02B.json`

## Not allowed changes

Product/test behavior, production code or migrations, fixture/reset semantics,
test skipping or sampling, lower/non-blocking coverage, shared mutable database
or storage namespaces, unpinned dependencies/actions, or alternate ownership
and provisioning paths outside `run_isolated_tests.py`.

## Acceptance criteria

- [ ] Canonical discovery recursively collects repository `backend/tests/**/test_*.py`
      nodes at the exact head; an immutable manifest binds head SHA, module,
      node ID, lane, collection exit, completion exit, skip/deselect state, and
      artifact digest.
- [ ] An independent validator rejects missing, duplicate, foreign, deselected,
      unexpectedly skipped, zero-collected, interrupted, and partially completed
      nodes and proves every canonical node completed exactly once.
- [ ] Four dependency lanes run concurrently in one job with distinct
      runner-created PostgreSQL databases/roles and distinct MinIO bucket/prefix
      namespaces; concurrency and bounded-cleanup tests reject collisions.
- [ ] Per-lane coverage artifacts are exact-head/digest bound and combined once;
      global 78% and all protected 90% commands remain unchanged and blocking.
- [ ] Real PostgreSQL/MinIO/API contracts, cleanup, timeout, signals, redaction,
      permissions, and upstream failure/cancellation custody remain mandatory.
- [ ] Exact hosted head records total Backend wall time, slowest lane, aggregate
      runner minutes, collected/completed counts, and coverage. More than eight
      minutes blocks completion unless the user explicitly accepts the measured
      risk; no gate may be weakened to meet the target.
- [ ] Konan remains the implementation author/contributor in Git history and PR
      evidence.

## Verification commands

```bash
cd backend
ruff check app tests scripts
python -m pytest -q tests/test_ci_test_lanes.py tests/test_isolated_database_runner.py
python scripts/run_test_lanes.py --collect-only --metadata-dir /tmp/workstream-lanes-collect
python scripts/validate_test_lane_evidence.py --metadata-dir /tmp/workstream-lanes-collect
python scripts/run_test_lanes.py --metadata-dir /tmp/workstream-lanes --summary-json /tmp/workstream-lanes.json --timeout-seconds 1200
python scripts/validate_test_lane_evidence.py --metadata-dir /tmp/workstream-lanes
coverage combine
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
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

Exact node custody, isolated services, coverage combination, fail-closed fan-in,
contributor attribution, and exact hosted resource/time evidence.

## Stop conditions

Stop if 02A evidence is incomplete, independent validation scope remains
unresolved, exact-node or coverage custody fails, services share mutable state,
or the hosted target requires a weakened gate.
