# Internal Review Evidence

## Chunk

`WS-CI-001-02B` — Exact-Custody Semantic Test Lanes

## Required Statements

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: cc8ee4f1a03305e8c6e5830cff012effa210959b

Reviewed at: 2026-07-24T16:30:32Z

Reviewer run IDs: ci02b_senior_review, ci02b_qa_review,
ci02b_security_review, ci02b_product_ops_review,
ci02b_restart_arch_review, ci02b_restart_ci_review, ci02b_contract_gap,
ci02b_source_audit, ci02b_test_delta_review, ci02b_bootstrap_senior,
ci02b_bootstrap_qa, ci02b_bootstrap_security, ci02b_bootstrap_ops,
ci02b_bootstrap_arch, ci02b_bootstrap_ci

After the reviewed SHA, only evidence and status files changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Independent UUID implementations must remain behavior-compatible. |
| QA/test | PASS | None | Exact inventory, failure custody, resource isolation, and timing evidence pass. |
| security/auth | PASS WITH LOW RISKS | None | A force-kill after bounded cleanup can leave local resources; hosted CI fails closed. |
| product/ops | PASS | None | Hosted operator evidence and Konan attribution are explicit; product behavior is unchanged. |
| architecture | PASS | None | Collection-only UUID stabilization restores runtime aliases before test bodies. |
| CI integrity | PASS | None | Ruff, API E2E, exact-node validation, coverage floors, and timing remain blocking. |
| docs | PASS | None | Operations and status documentation match the final workflow sequence. |
| reuse/dedup | PASS | None | Canonical isolation runner is reused; independent validator duplication is intentional. |
| test delta | PASS | None | Deleted shard tests are replaced without product-test weakening or deselection. |

The bootstrap repair review initially blocked publication because the reviewed
SHA was stale and this file had an extra blank line at EOF. Both evidence
defects are corrected here. All six repair reviewers accepted the fixed-path,
mode-700 evidence-root initialization; CI integrity found no weakened gate.

## Valid Findings Addressed

- Replaced invalid underscore-bearing MinIO bucket names with S3-valid,
  collision-tested lane namespaces and bound the real S3 test bucket to its
  owning lane.
- Removed the isolated-runner test exclusion. All runner self-test nodes remain
  canonical and execute under the explicit `admin_runner_self_test` kind while
  ordinary children never receive the admin database URL.
- Added an independent recursive pytest collection that rejects a
  self-consistent but missing or foreign runner manifest.
- Preserved full parametrized node IDs while stabilizing import-time UUIDv4
  parameters by exact head, callsite, line, and ordinal. Both plugins restore
  `uuid.uuid4` and repository import aliases before test bodies execute.
- Made negative process exits, skip, deselection, interruption, partial
  completion, digest drift, and shared database/storage/coverage custody fail.
- Removed intermediate coverage files after authenticated per-lane combination
  so the final workflow accepts exactly four public lane artifacts before one
  literal `coverage combine`.
- Added fail-closed hosted evidence for total Backend wall time, slowest lane,
  aggregate runner seconds, exact node counts, coverage percentage, and raw
  digests; total wall time above 480 seconds fails with no silent waiver.
- Redacted direct admin-runner logs and aligned the operations runbook with the
  actual hosted sequence and local diagnostic boundary.
- Added explicit fixed-path initialization of `.ci/test-lanes` before the first
  hosted collection. This closes the observed `invalid_lane_outputs` bootstrap
  failure without allowing the runner to create an unowned parent directory.

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
- 60 focused lane-runner and independent-validator tests passed.
- 100 Agent Gate tests passed.
- Two independent full collections agreed on 2,046 exact pytest nodes at the
  reviewed head; independent evidence validation passed.
- Merge intent, Markdown links, stale wording, and diff integrity passed.
- Local full service execution was not used as hosted performance evidence.

## Remaining Risks

- The exact GitHub Backend job must still prove real PostgreSQL and MinIO
  concurrency, API E2E, 78/90 coverage gates, and total wall time at or below
  480 seconds on the final PR head.
- A force-kill after the bounded cleanup grace can leave runner-owned resources
  on persistent local services. Evidence fails closed; operators must inspect
  and remove only exact recorded resources.
- The runner and independent validator intentionally duplicate the stable UUID
  collection specification. Their separate tests must prevent common-mode drift.
