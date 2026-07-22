# Chunk Contract: WS-CI-001-02A — Migrate-Once Semantic Test Lanes

## Parent initiative

`WS-CI-001` — Backend CI Acceleration

## Goal

Adopt and repair Konan's semantic-lane work so the complete Backend required
check runs in under eight minutes without weakening exact test execution,
service isolation, coverage, or failure custody.

## Why this chunk exists

PR #180 measured a material runtime improvement by migrating once per isolated
database process and partitioning tests by dependency. Review found missing
signed custody, node-level execution proof, strict assertions, complete trigger
restoration coverage, and prospective scope. This contract defines those
requirements before implementation is adopted.

## Risk class

L1 / P0 CI integrity

## SLA

P1

## Start phase

`implementation`

## Allowed files

- `.github/workflows/backend.yml`
- `backend/pyproject.toml`
- `backend/scripts/ci_test_shards.py` (deletion only)
- `backend/scripts/run_isolated_tests.py`
- `backend/scripts/run_test_lanes.py`
- database/test-infrastructure files under `backend/tests/` changed by PR #180
- `backend/tests/test_ci_test_shards.py` (deletion only)
- `backend/tests/test_ci_test_lanes.py`
- `backend/tests/test_database_reset.py`
- `backend/tests/test_isolated_database_runner.py`
- `docs/operations_backend_testing.md`
- `scripts/test_agent_gates.py`
- this initiative's status, review, and evidence files
- `.agent-loop/merge-intents/WS-CI-001-02A.json`

## Not allowed changes

- backend application code, production migrations, product behavior, or API;
- skipped, sampled, deselected, or silently unaccounted test nodes;
- truthiness substitutions for exact Boolean contract assertions;
- lower coverage floors, non-blocking failures, arbitrary shards, or shared
  mutable PostgreSQL databases/roles/storage namespaces;
- architecture refactoring of ProjectService, TaskService, or CheckerService.

## Acceptance criteria

- [ ] Every canonical backend test module and collected node is assigned and
      completed exactly once, with missing, duplicate, foreign, zero-collection,
      deselected, and unexpected-skip evidence rejected.
- [ ] Four semantic lanes run concurrently in one job; PostgreSQL lanes own
      distinct migrated databases and roles and coverage files remain isolated.
- [ ] The central reset preserves Alembic and immutable migration state and
      restores all seven canonical guarded-table triggers transactionally.
- [ ] All changed Boolean assertions retain exact `is True`/`is False` contracts.
- [ ] Real PostgreSQL migrations, locks, triggers, constraints, transactions,
      concurrency, MinIO, and API contract tests remain mandatory.
- [ ] Global 78% and every protected 90% floor remain unchanged and blocking.
- [ ] Cleanup, timeout, signals, redaction, and exact-head metadata fail closed.
- [ ] Exact hosted head proves the full Backend job under eight minutes, or the
      PR reports the miss without weakening gates.
- [ ] Konan remains the implementation author/contributor in Git history and PR
      evidence.

## Verification commands

```bash
cd backend
ruff check app tests scripts
python -m pytest -q tests/test_ci_test_lanes.py tests/test_database_reset.py tests/test_isolated_database_runner.py
rm -f .coverage .coverage.*
python scripts/run_test_lanes.py --metadata-dir /tmp/workstream-lanes --summary-json /tmp/workstream-lanes.json --timeout-seconds 1200
coverage combine
coverage report --precision=2 --fail-under=78
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

Node-level exact execution, destructive reset containment, trigger restoration,
coverage custody, contributor attribution, and hosted wall time.

## Stop conditions

Stop if 02A lacks a signed implementation start, any test/coverage assertion
must be weakened, production behavior is required, contributor authorship would
be lost, or exact hosted evidence cannot be tied to the reviewed head.
