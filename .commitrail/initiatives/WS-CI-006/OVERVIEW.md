# WS-CI-006 — Change-impact backend verification

- Disposition: Planned
- Next usable boundary: [WS-CI-006-01](WS-CI-006-01.md)

## Intent

Reduce routine backend pull-request feedback by running the tests affected by a
change, while keeping the required result trustworthy. A narrow change should
not wait for every unrelated subsystem; changes whose impact cannot be proven
must still run the full suite.

## Current evidence

- `backend/scripts/test_lane_catalogue.py` assigns every discovered test module
  to the complete backend run. `backend/scripts/run_test_lanes.py` then
  deterministically hash-partitions node IDs within shared, project, and task
  groups; these partitions are not an impact map.
- `.github/workflows/backend.yml` always schedules nine backend lanes, a
  separate authorization-boundary preflight, MinIO image construction, and a
  final real-API/evidence aggregation job.
- Run [36724982896](https://github.com/Flow-Research/workstream/actions/runs/36724982896)
  on 2026-09-30 completed 7,918 tests, zero skipped/deselected, in about 44
  minutes. Three lane jobs began about 21 minutes after the first six; the
  longest lane then ran about 17 minutes. This is one observed run, not a
  universal baseline.
- `CONTRIBUTING.md` currently requires hosted full suites. Selective PR checks
  therefore require an explicit, reviewed policy update—not merely a workflow
  optimization.

## Design direction

- Use a deterministic repository-owned changed-source-to-test ownership map;
  do not add an external test-impact service or trust mutable historical
  selector state.
- Start with one narrow reviewed mapping only: changes confined to
  `backend/app/core/s3_validation.py` select its direct configuration contract
  tests, provider-neutral namespace-conformance tests, and real S3/MinIO adapter
  tests. Changes to its callers, shared test support, schemas/migrations,
  dependencies, or CI-selection machinery select the complete suite. No other
  application-source path is selective initially.
- Keep `.commitrail/**` in the exact change manifest, but exclude it only when
  classifying backend source impact: every bounded product PR carries a durable
  change record. Every PR that changes Commitrail metadata also runs the
  backend policy-semantics module that reads specific planning files. A
  metadata-only PR still runs that module, Markdown/stale-doc gates, and the
  non-empty authorization/static preflight; other documentation paths remain
  full-suite unless separately reviewed.
- Bind selection to the exact PR base, head, synthetic merge execution SHA/tree,
  merge-base, changed-path digest, impact-map digest, test-inventory digest,
  and selected test/job manifest. A mismatch, missing Git object, stale
  candidate, changed test support, or unreviewed path selects the complete
  suite. Changes within mapped test modules run the complete mapped closure;
  new or unmapped tests and shared test fixtures select the full suite.
- Keep the required Backend workflow and final check present on every PR. Do
  not use GitHub workflow path filters to suppress a required status.
- Run shared lint/docstring and authorization-boundary checks once, not once per
  test lane. Keep full public-API E2E and service startup in full mode unless a
  reviewed impact mapping specifically requires it. Reuse the pinned MinIO
  build by exact source-input digest, not commit SHA; verify cache contents
  before tests.
- Make the selected impact set the PR gate. Keep full-suite execution available
  for broad changes and manual runs, and run the complete suite nightly on
  `main`. A failed nightly audit remains failed and requires diagnosis of the
  map or product/test defect; it does not silently green PR checks or substitute
  for exact-PR evidence. Never describe a scheduled result as proof for another
  PR head.
- Preserve real PostgreSQL, S3-protocol, concurrency, migration, and public API
  checks whenever their owner paths are selected. The five-minute target is
  for routine narrow changes, not broad/security/schema changes or runner
  outages; hosted wall time remains measured, not promised.
- Leave test bodies, assertions, coverage policy, product behavior, and
  external review requirements unchanged.

## Proposed boundary

1. **WS-CI-006-01:** implement the exact-target impact manifest, the initial
   S3-validation mapping, conservative full-suite fallback, selected-node/job
   evidence validation, and CI integration; change `AGENTS.md` and
   `CONTRIBUTING.md` in the same PR; prove the selector adversarially and run
   the complete suite on the candidate.
2. Add further source/test ownership mappings only when their complete
   consumer-test closure and shared-fixture/infrastructure dependencies are
   demonstrated. Unmapped application code remains full-suite. Do not add a
   mapping just to claim a broader speedup.

## Risks and controls

- **False-negative selection:** exact ownership coverage, full-suite fallback
  for unknown or cross-cutting paths, mapping mutation probes, plus scheduled
  full-suite audits.
- **Stale or mismatched evidence:** exact base/head, tree and manifest digests;
  execution tree must be the exact GitHub PR merge candidate whose parents are
  the event base and head; no cached result may attest to another source tree.
- **Broken branch protection:** workflow and final required status always run;
  preserve the existing required `test` context, distinguish expected
  unselected jobs from missing selected jobs using the digest-bound
  manifest, and reject an empty test selection. No path-filtered required
  workflow.
- **Misleading performance claim:** report selected test count and hosted wall
  time separately; the selector-changing PR itself full-fallbacks. Wait for the
  first later naturally eligible mapped PR before reporting narrow-mode hosted
  timing; retain full execution for risky changes and do not claim every PR is
  under five minutes.

## Non-goals

- No test deletion, skipping, weakened assertions, coverage threshold, arbitrary
  shard expansion, runner-provider change, new service, or agent-controlled
  selection authority.
- No changes to product code or test behavior.
