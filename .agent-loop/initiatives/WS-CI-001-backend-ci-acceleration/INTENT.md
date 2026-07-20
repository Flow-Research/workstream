# INTENT: WS-CI-001 - Backend CI Acceleration

## Problem being solved

The required Backend GitHub Actions job runs the complete backend test suite in
one sequential process. PR #161 spent 25 minutes 31 seconds in that single step
and about 27 minutes overall even though it changed no backend product code.

## Why this work matters

Every implementation PR must retain full backend and subsystem coverage proof,
but a 25-to-50-minute feedback loop slows review, repair, and safe delivery. The
repository needs shorter wall-clock feedback without weakening its zero-trust
CI evidence.

## Current behavior

- One Ubuntu job provisions PostgreSQL and MinIO.
- One isolated database is migrated and used for all 999 collected tests across
  31 test modules.
- The full suite writes one coverage data file.
- Twelve coverage reports and the API contract E2E run only after the full suite.
- The isolated runner buffers child output, so the longest step exposes no live
  progress.
- PR #161 spent only 20 seconds installing dependencies; dependency setup is not
  the primary bottleneck.

## Target behavior

- Every collected backend test still runs on every required Backend workflow.
- Canonical filesystem test modules are assigned exactly once. Stable test-base
  cardinality signatures bind runtime inventory to preflight, while each shard
  proves its exact same-process collection equals its completions.
- Each shard receives an independently owned migrated PostgreSQL database.
- Coverage artifacts are combined centrally before the unchanged 78 percent
  repository floor and 90 percent protected-subsystem floors are enforced.
- The API contract E2E proof runs concurrently with test shards.
- The final required Backend check fails closed on missing, duplicate, failed,
  cancelled, malformed, foreign-tree, or byte-tampered shard evidence.
- CI exposes shard progress and timing evidence.

## Design chosen

Use deterministic file-level sharding based on the collected test inventory.
Keep each test module intact, distribute modules using collected test counts,
run shards in independent GitHub jobs, upload uniquely named coverage artifacts,
and combine them in one final required `test` job. File-level isolation avoids
introducing unsafe concurrency inside a shared database and requires no new
pytest scheduling dependency.

## Alternatives considered

- Skip the Backend workflow for engineering-loop PRs: rejected for the first
  chunk because the user requires full-suite proof and path routing can hide an
  incorrectly classified backend-affecting change.
- Add `pytest-xdist` inside the existing job: rejected because tests share one
  migrated database and many modules exercise transaction and migration state.
- Hash node IDs across shards: rejected because it splits module fixtures and
  makes database-sensitive module behavior harder to reason about.
- Preserve one sequential process but add caching: rejected as the primary fix;
  installation was 20 seconds while the suite was more than 25 minutes.
- Lower or sample coverage: rejected as CI weakening.

## Boundaries preserved

- All tests, migrations, real PostgreSQL behavior, required MinIO behavior, API
  contract proof, and coverage thresholds remain mandatory.
- No backend application, schema, migration, authentication, authorization,
  artifact, review, contribution, compensation, or payment behavior changes.
- The final branch-protection check identity remains stable.
- No third-party test-sharding service or production secret is introduced.
- Human PR approval and existing Agent Gates remain unchanged.

## Expected risks

- A planner may omit or duplicate a test module.
- Coverage artifacts may be mixed across commits or shards.
- One oversized module may dominate a shard and limit speedup.
- GitHub matrix cancellation may accidentally allow the aggregator to pass.
- MinIO-dependent tests may be assigned to jobs without MinIO.
- Coverage path differences may prevent correct combination.
- GitHub concurrency and aggregate runner minutes may increase.

## What must not change

- No test may be skipped because of its shard assignment.
- No assertion, coverage floor, required check, or failure propagation may be
  weakened.
- Shards must never share a database or database role.
- Coverage from a different commit or incomplete shard set must not validate.
- `WS-ENG-001-04B` remains inactive.

## How this will be proven

Unit tests will prove filesystem and stable node-signature inventory completeness,
determinism, exact same-process collection/completion, stable ordering, malformed input
rejection, and fail-closed coverage-manifest validation. Workflow review will
prove isolated services and databases, immutable action pins, checked-out-tree
binding, byte-hashed artifacts, complete fan-in, unchanged thresholds, stable
required-check identity, and no skipped failure path. The implementation PR must
run the old full suite locally where practical and the new hosted matrix on the
exact checked-out tree; measured wall time will be compared with PR #161's
25-minute-31-second full-suite baseline.

## Human decisions required

- Approve implementation of `WS-CI-001-01` after plan review.
- Decide after hosted evidence whether four shards are the correct cost/latency
  balance or should be adjusted in a later chunk.
- Separately approve any later path-routing policy; it is not part of 01.
