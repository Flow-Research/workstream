# PR Trust Bundle

## Chunk

`WS-CI-001-02B` — Exact-Custody Semantic Test Lanes

Merge intent: `.agent-loop/merge-intents/WS-CI-001-02B.json`

## Goal

Replace arbitrary Backend shards with four concurrent dependency lanes while
proving every canonical pytest node, isolated resource, coverage byte, and
hosted timing outcome on the exact PR head.

## Human-approved intent

- Initiative plan: `../PLAN.md`
- Chunk contract: `../chunks/WS-CI-001-02B-exact-custody-semantic-test-lanes.md`

## Signed Start Provenance

- Signed start run: `30101104403`
- Authorized main SHA: `bcf1292e1a591e3e84bf8ee212ee7191d80741fa`
- Phase: `implementation`
- Contract path: `.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/chunks/WS-CI-001-02B-exact-custody-semantic-test-lanes.md`
- Signed contract blob SHA: `784bae53f72f6460b4b74799c1c9b1519565dabe`
- Reviewed implementation SHA: `24f3b638b175352ddce3548d8c247b65c3328087`

Only independently verified signed automation state is canonical authority.
PR prose and checked boxes are navigation evidence, not authorization.

## What changed

- Replaced the four-job shard matrix and artifact fan-in with one required job
  orchestrating four concurrent semantic test lanes.
- Added exact recursive node collection, independent recollection/validation,
  authenticated per-lane evidence, and exactly one coverage combination.
- Extended the canonical isolated runner with per-lane PostgreSQL and MinIO
  namespace custody, redaction, heartbeat, and bounded cleanup evidence.
- Pinned and asserted Ruff `0.15.22` in the workflow to remove resolver drift.
- Added hosted exact-head timing, node-count, coverage, and digest evidence.
  The evidence records whether the 480-second target is met; after the owner
  explicitly accepted the measured miss, timing no longer overrides passing
  correctness and coverage gates.
- Initialized the fixed `.ci/test-lanes` evidence root with mode 700 before the
  first collection, closing the hosted `invalid_lane_outputs` bootstrap failure.
- Preserved schema-lane ordinary coverage when its direct admin self-test unit
  legitimately emits no `app` coverage; missing ordinary coverage remains a
  hard failure.
- Rejected and reverted a six-process experiment after exact hosted evidence
  showed CPU contention. Rebalanced the existing four isolated processes as
  `shared_foundations`, `schema_contracts`, `project_lifecycle`, and
  `task_lifecycle` without changing the final workflow contract or gates.
- Addressed fourteen external findings across failure observability, stable Git
  errors, MinIO interrupts, independent pytest environment isolation, UUID
  teardown, workflow failure-gate regression protection, and exact operations
  wording. Partial startup and unexpected orchestration failures now retain
  four explicit failed lane rows without becoming acceptable evidence.
- Deleted the obsolete shard runner and shard tests and updated operations docs.

## Why it changed

The prior shard topology duplicated services and artifact fan-in while Backend
CI remained slow. An unbounded Ruff resolver update produced observed lint
drift across the required Backend check until this chunk pinned `0.15.22`.
The replacement must improve critical-path time without hiding tests, sharing
mutable resources, weakening coverage, or trusting self-authored evidence.

## Design chosen

One job starts pinned PostgreSQL and MinIO services, then a repository-owned
orchestrator runs four dependency lanes concurrently. Ordinary lanes delegate
resource custody to `run_isolated_tests.py`; its own self-tests execute as a
separately classified admin phase inside canonical node evidence. An independent
validator recollects current pytest nodes and verifies exact head, nodes,
resources, coverage bytes, failures, and timings before combination.

## Alternatives rejected

- Wholesale cherry-pick of `e22e9fba`/`c73b2893`: rejected because it changed
  forbidden product tests, initiative artifacts, and lacked exact node custody.
- Keep arbitrary shards: rejected because it preserves duplicated services and
  artifact fan-in rather than dependency ownership.
- Trust the runner manifest: rejected because one writer could omit nodes while
  producing self-consistent evidence.
- Strip parameterized IDs: rejected because it loses exact node identity.
- Ignore new Ruff findings or loosen lint: rejected as CI weakening.

## Scope control

### Allowed files changed

- `.github/workflows/backend.yml`
- `backend/scripts/ci_test_shards.py` (deleted)
- `backend/scripts/run_isolated_tests.py`
- `backend/scripts/run_test_lanes.py`
- `backend/scripts/validate_test_lane_evidence.py`
- `backend/tests/test_ci_test_shards.py` (deleted)
- `backend/tests/test_ci_test_lanes.py`
- `backend/tests/test_isolated_database_runner.py`
- `backend/tests/test_test_lane_evidence.py`
- `docs/operations_backend_testing.md`
- `scripts/test_agent_gates.py`
- Initiative status, two review files, and one merge intent

### Files outside scope

- None.

## Product Behavior

- [x] No Workstream product behavior changed.

## Acceptance criteria proof

- [x] Recursive exact-node inventory with no exclusion escape — 2,056 nodes
  independently recollected and validated at the reviewed head.
- [x] Four concurrent dependency lanes with distinct database/role and MinIO
  bucket/prefix custody — implementation and adversarial tests pass; hosted
  service proof remains required.
- [x] Missing, duplicate, foreign, skipped, deselected, interrupted, partial,
  digest-drifted, and shared-custody evidence fails in focused tests.
- [x] Exactly four authenticated coverage artifacts precede one literal
  `coverage combine`; global 78 and every protected 90 floor remain blocking.
- [x] Hosted evidence records wall, slowest lane, aggregate runner seconds,
  counts, coverage, digests, and the explicit 480-second target outcome.
- [x] Konan remains a Git contributor through the immutable `Co-authored-by`
  trailer on implementation commit `161417ff`; eligible source commits are
  `e22e9fba` and `c73b2893`. Later custody repairs are Abiorh-authored.

## Tests/checks run

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

Result summary: Ruff passed; 89 focused non-service tests passed and all 11
service-backed runner tests remain mandatory in hosted CI; 100 Agent Gates
passed; exact collection and independent recollection agreed on 2,056 nodes;
merge intent,
links, stale wording, and diff integrity passed.

## Test delta

### Tests added

- Semantic-lane orchestration and exact inventory tests.
- Independent evidence-validator corruption and real recollection tests.
- MinIO namespace, cleanup, redaction, signal, and timing custody tests.

### Tests modified

- Isolated-runner lifecycle tests and Agent Gate workflow regression tests.

### Tests removed/skipped

- Deleted only `test_ci_test_shards.py` with its obsolete shard implementation.
- No product test was skipped, deselected, removed, or weakened.

## CI integrity

- [x] Coverage thresholds unchanged and blocking
- [x] Exact Ruff pin removes resolver drift without suppressions
- [x] No typecheck or package-script weakening
- [x] No test, coverage, custody, service-contract, or failure-gate weakening;
      no `continue-on-error` or path suppression
- [x] No unpinned new GitHub Action or service image
- [x] Checkout credential persistence disabled
- [ ] Exact final GitHub Backend job passes; hosted evidence records the
      accepted miss against the 480-second performance target

## External review

External review response file, if findings are posted:

- `WS-CI-001-02B-external-review-response.md`

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Addressed | Fourteen inline findings reconciled; refreshed review remains pending. |
| GitHub checks | Pending | Exact final head must pass Agent Gates and Backend. |

## Reviewer results

Reviewed code SHA: `1526ade7b0bb320a9b0673f7871f409c2ef4724c`

Reviewed at: `2026-07-25T15:06:39Z`

Reviewer run IDs: `ci02b_cr_senior`, `ci02b_cr_qa`, `ci02b_cr_security`,
`ci02b_cr_ops`, `ci02b_cr_arch`, `ci02b_cr_ci`, `ci02b_cr_docs`,
`ci02b_cr_reuse`, `ci02b_cr_test_delta`.

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Accepted timing evidence is clear; correctness remains fail closed. |
| QA/test | PASS | None | Timing semantics and existing acceptance criteria are regression protected. |
| security/auth | PASS | None | Permissions, redaction, and resource custody remain intact. |
| product/ops | PASS | None | Product and contribution workflows are unchanged. |
| architecture | PASS | None | Acceptance remains evidence, not workflow bypass logic. |
| CI integrity | PASS | None | Tests, coverage, custody, API, and failures remain blocking. |
| docs | PASS WITH LOW RISKS | None | Canonical runbook and evidence use one timing convention. |
| reuse/dedup | PASS | None | No duplicate timing convention or validator path remains. |
| test delta | PASS | None | No removed, skipped, deselected, or weakened tests. |

## Remaining risks

- The final workflow repair still needs exact-head hosted PostgreSQL/MinIO, API
  E2E, complete coverage, and timing evidence. Run `30123755007` passed every
  functional and coverage gate at `cd1e8a8f` and measured about nine minutes;
  it predates the accepted-risk workflow repair and is not final-head proof.
- Persistent local services can retain exact runner-owned resources if forced
  cleanup exceeds its bounded grace; evidence fails and operators must inspect
  only the recorded resource identities.

## Follow-up work

After merge and automated memory reconciliation, stop. `WS-CI-001-03` remains
future planning only and is not declared as a successor.

## Human review focus

- Exact node custody and independent recollection.
- Admin credential isolation and real S3 bucket ownership.
- Exactly four coverage files, one combine, and unchanged 78/90 floors.
- Hosted wall time and aggregate runner evidence.
- Konan attribution and bounded repair authorship.

## Human ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
