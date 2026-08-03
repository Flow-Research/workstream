# Chunk Contract: WS-CI-001-03 — Distributed Semantic Test Lanes

## Goal

Restore real hosted parallelism for exact-custody semantic backend lanes,
partition the measured Alembic long tail, and stop duplicate unchanged-head
runs without weakening any test,
integration proof, failure propagation, or coverage threshold.

## Evidence for the change

Backend run `30782031524`, job `91588477886`, completed successfully in 17m20s.
The four lanes occupied 15m31s inside one `ubuntu-latest` job. Installation took
23 seconds and collection/validation took 19 seconds. The workflow also runs on
`pull_request_review`, repeating the complete Backend workflow for an unchanged
PR head. The earlier four-job topology completed near nine minutes before it was
replaced by single-runner semantic lanes.

## Risk class

L1 — required CI topology and evidence custody.

## Machine-checkable scope

```chunk-scope-json
{
  "schema_version": 1,
  "chunk_id": "WS-CI-001-03",
  "phase": "implementation",
  "risk_class": "L1",
  "allowed_paths": [
    ".github/workflows/backend.yml",
    ".github/workflows/agent-gates.yml",
    "backend/scripts/run_test_lanes.py",
    "backend/scripts/merge_test_lane_evidence.py",
    "backend/scripts/validate_test_lane_evidence.py",
    "backend/tests/test_ci_test_lanes.py",
    "backend/tests/test_merge_test_lane_evidence.py",
    "backend/tests/test_test_lane_evidence.py",
    "scripts/test_lightweight_agent_gates.py",
    "docs/operations_backend_testing.md",
    ".agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/INTENT.md",
    ".agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/DISCOVERY.md",
    ".agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/PLAN.md",
    ".agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/CHUNK_MAP.md",
    ".agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/STATUS.md",
    ".agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/RISKS.md",
    ".agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/DECISIONS.md",
    ".agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/chunks/WS-CI-001-03-safe-routing-cache-timing-reassessment.md",
    ".agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/reviews/WS-CI-001-03-internal-review-evidence.md",
    ".agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/reviews/WS-CI-001-03-pr-trust-bundle.md"
  ],
  "forbidden_paths": ["backend/app/**", "backend/alembic/**", "frontend/**"],
  "required_reviewers": ["senior engineering", "qa/test", "security/auth", "ci integrity", "test delta"],
  "verification_commands": ["focused-lane-tests", "workflow-static-check", "markdown-links", "stale-wording", "git-diff-check", "hosted-backend-exact-head"]
}
```

## Allowed changes

- Run the existing semantic ownership on five GitHub matrix jobs. Partition
  `test_alembic.py` node IDs deterministically across two schema lanes.
- Add one fail-closed helper that accepts exactly one digest-bound bundle per
  declared lane and emits the existing complete-run evidence schema.
- Keep final job ID `test` as the stable required `Backend / test` context.
- Remove the `pull_request_review` trigger from Backend, move the existing
  dependency-approval refresh to lightweight Agent Gates, and cancel superseded
  same-PR Backend runs.
- Update focused tests, operator documentation, and this initiative's records.

## Not allowed

- Skipping, sampling, deselecting, removing, or weakening tests.
- Lowering the global 78 percent or protected 90 percent coverage floors.
- Path-based Backend suppression or changed-file-only test execution.
- Shared mutable databases, MinIO namespaces, or coverage files.
- Product code, API, migration, schema, dependency, or branch-protection changes.
- Accepting missing, duplicate, foreign-head, digest-mismatched, failed,
  cancelled, or incomplete lane evidence.

## Acceptance criteria

- [ ] Five named semantic lanes run on five independent hosted matrix jobs.
- [ ] Every Alembic node maps deterministically to exactly one of two schema
      lanes; reset and isolated-runner contracts remain in schema A.
- [ ] Every lane provisions its own PostgreSQL service, migrated database/role,
      MinIO namespace, coverage file, and exact collection/completion evidence.
- [ ] Final `Backend / test` runs even after an upstream failure and explicitly
      rejects any non-success matrix result.
- [ ] Fan-in accepts exactly five fixed lane names, identical manifests and
      heads, digest-bound files, and no symlink or surplus lane directory.
- [ ] Independent final collection reconciles every canonical node exactly once
      against completed nodes before coverage is combined.
- [ ] Existing API E2E, global coverage, and every protected coverage report
      remain blocking.
- [ ] Backend runs only for PR synchronization/open/reopen and pushes to main;
      review submission/dismissal does not rerun an unchanged SHA.
- [ ] Guide dependency review submissions/dismissals refresh Agent Gates, where
      the unchanged exact-head approval check remains blocking.
- [ ] A newer run for the same PR cancels its superseded predecessor.
- [ ] Exact-head hosted evidence demonstrates the complete required check and
      records whether the eight-minute target is met.

## Verification

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest -q \
  backend/tests/test_ci_test_lanes.py \
  backend/tests/test_merge_test_lane_evidence.py \
  backend/tests/test_test_lane_evidence.py
PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

Hosted acceptance requires `Backend / test` on GitHub's exact checked-out PR
merge tree for the current PR head. Agent Gates separately binds exceptional
dependency approval to the literal PR head. Local timing is not acceptance
evidence.
