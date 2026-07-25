# Internal Review Evidence

## Chunk

`WS-CI-001-02B` — Exact-Custody Semantic Test Lanes

## Required Statements

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 400be486863e6eb83a6343e872763b9076770537

Reviewed at: 2026-07-25T15:42:43Z

Reviewer run IDs: ci02b_cr_senior, ci02b_cr_qa, ci02b_cr_security,
ci02b_cr_ops, ci02b_cr_arch, ci02b_cr_ci, ci02b_cr_docs,
ci02b_cr_reuse, ci02b_cr_test_delta

The reviewed SHA includes current trusted main through PR #200 and the final
CodeRabbit repair. After it, only this final evidence reconciliation changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Redacted tracebacks and cancellation cleanup are maintainable. |
| QA/test | PASS | None | Failure diagnostics, redaction, and cancellation are regression protected. |
| security/auth | PASS WITH LOW RISKS | None | Known workflow secrets are redacted; broader pattern hardening is deferred. |
| product/ops | PASS | None | No product, compensation, review-decision, or reputation behavior changed. |
| architecture | PASS | None | Runner ownership and failure-evidence boundaries remain intact. |
| CI integrity | PASS WITH LOW RISKS | None | Gate posture is unchanged; current secret inputs are covered. |
| docs | PASS | None | Exact commands and all seventeen findings are reconciled. |
| reuse/dedup | PASS | None | Existing cleanup and finalization paths remain reused. |
| test delta | PASS | None | No tests weakened; five focused repair cases pass. |

The bootstrap repair review initially blocked publication because the reviewed
SHA was stale and this file had an extra blank line at EOF. Both evidence
defects are corrected here. All six repair reviewers accepted the fixed-path,
mode-700 evidence-root initialization; CI integrity found no weakened gate.

The exact-head coverage repair review found no code blocker. Successful lanes
still require non-symlink ordinary coverage; an admin runner self-test coverage
file is combined only when it exists because that direct self-test process can
legitimately collect no `app` data. Failed lanes retain nonzero exit evidence
instead of allowing missing coverage to mask the original failure. Optional
admin coverage absence remains a documented low diagnostic risk, not a product
coverage or exact-node custody bypass.

## Valid Findings Addressed

- Replaced invalid underscore-bearing MinIO bucket names with S3-valid,
  collision-tested lane namespaces and bound the real S3 test bucket to its
  owning lane.
- Removed the isolated-runner test exclusion. All runner self-test nodes remain
  canonical and execute under the explicit `admin_runner_self_test` kind while
  ordinary children never receive the admin database URL.
- Added an independent recursive pytest collection that rejects a
  self-consistent but missing or foreign runner manifest.
- Preserved full parameterized node IDs while stabilizing import-time UUIDv4
  parameters by exact head, callsite, line, and ordinal. Both plugins restore
  `uuid.uuid4` and repository import aliases before test bodies execute.
- Made negative process exits, skip, deselection, interruption, partial
  completion, digest drift, and shared database/storage/coverage custody fail.
- Removed intermediate coverage files after authenticated per-lane combination
  so the final workflow accepts exactly four public lane artifacts before one
  literal `coverage combine`.
- Added hosted evidence for total Backend wall time, slowest lane, aggregate
  runner seconds, exact node counts, coverage percentage, raw digests, and the
  explicit 480-second target outcome. Correctness and coverage remain
  fail-closed; the owner-accepted performance miss is recorded rather than
  overriding those results.
- Redacted direct admin-runner logs and aligned the operations runbook with the
  actual hosted sequence and local diagnostic boundary.
- Added explicit fixed-path initialization of `.ci/test-lanes` before the first
  hosted collection. This closes the observed `invalid_lane_outputs` bootstrap
  failure without allowing the runner to create an unowned parent directory.
- Repaired schema-lane coverage finalization after hosted run `30109561363`
  proved that its ordinary unit emitted coverage while the direct admin
  self-test unit legitimately emitted none. Missing ordinary coverage still
  fails closed, and regression tests cover both paths.
- Rejected the six-process execution-unit experiment after hosted run
  `30118538144` proved it increased CPU contention. The experiment and its
  temporary tests were reverted without weakening the four-lane contract.
- Rebalanced the four isolated processes around measured hotspots:
  `project_lifecycle`, `task_lifecycle`, `schema_contracts`, and
  `shared_foundations`. Retired lane names were removed from the runner,
  focused tests, runbook, and current status.
- Reconciled all fourteen CodeRabbit findings. Failure paths now preserve a
  stable Git error, process interrupts, missing isolation metadata, collection
  precedence, and exactly four failed lane rows across runtime and partial
  startup failures. Independent recollection clears inherited pytest injection,
  UUID teardown is unconditional, and Agent Gates bind the explicit `run.exit`
  failure step.

## Commands Run

```bash
cd backend
ruff check app tests scripts
python -m pytest -q tests/test_ci_test_lanes.py tests/test_test_lane_evidence.py
python scripts/run_test_lanes.py --collect-only --metadata-dir "$tmp/collect" --summary-json "$tmp/collect-summary.json"
python scripts/validate_test_lane_evidence.py --metadata-dir "$tmp/collect" --summary-json "$tmp/collect-summary.json"
cd ..
python3 scripts/test_agent_gates.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
python3 scripts/check_markdown_links.py docs/operations_backend_testing.md .agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/STATUS.md
git diff --check origin/main...HEAD
```

## Results

- Ruff passed with exact local `ruff 0.15.22`.
- 89 focused lane-runner, isolated-runner, and independent-validator tests
  passed without local service authority; 11 service-backed cases remain
  mandatory in hosted CI and are not skipped by the workflow.
- 100 Agent Gate tests passed.
- Exact collection and independent recollection agreed on 2,056 pytest nodes
  before the timing-only workflow repair; final exact-head hosted recollection
  remains required.
- Merge intent, Markdown links, stale wording, and diff integrity passed.
- Local full-service execution was not used as hosted performance evidence.

## Remaining Risks

- The exact GitHub Backend job must still prove real PostgreSQL and MinIO
  concurrency, API E2E, 78/90 coverage gates, and record its 480-second target
  outcome on the final PR head. Prior run `30118538144` passed functional
  and coverage custody but failed timing for the now-reverted six-process
  experiment; it is diagnostic evidence, not completion proof.
- A force-kill after the bounded cleanup grace can leave runner-owned resources
  on persistent local services. Evidence fails closed; operators must inspect
  and remove only exact recorded resources.
- The runner and independent validator intentionally duplicate the stable UUID
  collection specification. Their separate tests must prevent common-mode drift.
