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
- Bind selection to the exact PR base/head and a machine-validated manifest.
  Changed tests always run. A path with no reviewed mapping, shared fixtures,
  schema/migration/dependency changes, or CI-selection changes conservatively
  selects the complete suite.
- Keep the required Backend workflow and final check present on every PR. Do
  not use GitHub workflow path filters to suppress a required status.
- Make the selected impact set the PR gate. Keep full-suite execution available
  for broad changes, manual runs, and a scheduled main-branch audit. Never
  describe the scheduled full-suite result as proof for a different PR head.
- Preserve real PostgreSQL, S3-protocol, concurrency, migration, and public API
  checks whenever their owner paths are selected. The five-minute target is
  for routine narrow changes, not broad/security/schema changes or runner
  outages; hosted wall time remains measured, not promised.
- Leave test bodies, assertions, coverage policy, product behavior, and
  external review requirements unchanged.

## Proposed boundary

1. **WS-CI-006-01:** implement the exact-base impact manifest, conservative
   fallback, selected-node evidence validation, and CI integration; change the
   contributor policy in the same PR; prove selection decisions with adversarial
   tests and the required full suite on the candidate.
2. Add source/test ownership mappings incrementally only when their consumer
   coverage and shared-fixture edges are demonstrated. Unmapped code remains
   full-suite. Do not create follow-on PRs solely to satisfy this overview.

## Risks and controls

- **False-negative selection:** exact ownership coverage, full-suite fallback
  for unknown or cross-cutting paths, mapping mutation probes, plus scheduled
  full-suite audits.
- **Stale or mismatched evidence:** exact base/head, tree and manifest digests;
  no cached result may attest to a different source tree.
- **Broken branch protection:** workflow and final required status always run;
  no path-filtered required workflow and no empty-selection success.
- **Misleading performance claim:** report selected test count and hosted wall
  time separately; retain full execution for risky changes and report measured
  results rather than claiming every PR is under five minutes.

## Non-goals

- No test deletion, skipping, weakened assertions, coverage threshold, arbitrary
  shard expansion, runner-provider change, new service, or agent-controlled
  selection authority.
- No changes to product code or test behavior.
