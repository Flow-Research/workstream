# Chunk Contract: WS-CI-001-01R1 — Timeout Cleanup Repair

## Parent initiative

`WS-CI-001` — Backend CI Acceleration

## Goal

Ensure repository-owned isolated runners time out before their enclosing GitHub
jobs so they retain operational headroom to terminate child processes and clean
up exact owned database resources.

## Why this chunk exists

PR #163 merged before its final CodeRabbit comment was repaired. The comment
correctly identified child timeouts longer than their enclosing job budgets.

## Risk class

L1

## Allowed files

```text
.github/workflows/backend.yml
backend/scripts/ci_test_shards.py
scripts/test_agent_gates.py
.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/**
.agent-loop/merge-intents/WS-CI-001-01R1.json
```

## Not allowed

```text
backend/app/**
backend/alembic/**
dependency changes
test skips or coverage threshold changes
job timeout increases
path-based workflow suppression
WS-CI-001-02 activation
```

## Acceptance criteria

- [x] Shard child timeout is below the 90-minute job budget with a configured
      gap of at least 10 minutes.
- [x] API E2E child timeout is below the 30-minute job budget with a configured
      gap of at least 5 minutes.
- [x] Workflow regression tests bind the timeout values and budget gaps.
- [x] Real isolated-runner cleanup tests pass against PostgreSQL.
- [x] External review response and PR trust evidence are updated.
- [x] Required internal reviewers confirm the exact rebased repair head.
- [ ] Hosted Backend, Agent Gates, and external review pass.

## Verification commands

```text
cd backend && python -m pytest -q tests/test_ci_test_shards.py tests/test_coverage_contract.py
cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-url> python -m pytest -q tests/test_isolated_database_runner.py
python -m pytest -q scripts/test_agent_gates.py
python scripts/check_markdown_links.py
python scripts/check_stale_workstream_wording.py
python scripts/check_loop_memory_state.py
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Confirm the child budgets remain operationally sufficient, are strictly below
the job budgets, and preserve cleanup and failure propagation without weakening
the full-suite proof.
