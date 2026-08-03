# DECISIONS: WS-CI-001 - Backend CI Acceleration

## 2026-08-03 - Partition the measured Alembic long tail

Hosted Backend run `30786185424` (schema job `91600051005`) proved that the
semantic matrix runs in parallel, but `tests/test_alembic.py` alone took 707.60
seconds and dominated a 13m09s schema job. Partition its exact collected
node IDs deterministically across two schema runners. Keep reset and isolated
runner contracts in schema A, and reconcile all five lane manifests at fan-in
so no test can be skipped or counted twice.

## 2026-07-20 - Prioritize CI acceleration before explicit-start automation

The user selected backend CI efficiency as the next initiative after successful
merge and live verification of `WS-ENG-001-04A`. `WS-ENG-001-04B` remains
stopped and is not implicitly reprioritized by merge memory.

## 2026-07-20 - Preserve the full suite

The first implementation will reduce wall-clock time through isolated parallel
execution, not by skipping tests or lowering coverage.

## 2026-07-20 - Use file-level shards without a new scheduling dependency

Test modules remain intact and are assigned deterministically from collected
inventory. Shared-database xdist and third-party sharding services are rejected.

## 2026-07-20 - Keep routing separate

Path-based workflow routing, caches, and persistent runtime weighting require
separate evidence and approval after parallel execution is proven.

## 2026-07-20 - Preimplementation review repairs accepted

Nine reviewer tracks required canonical filesystem and collected-node inventory,
exact observed-node fan-in, coverage-byte hashing, checked-out-tree provenance,
fixed artifact sets, explicit read-only permissions, digest-pinned PostgreSQL,
stable `Backend / test`, canonical operator documentation, and a real local dry
run. The plan and 01 contract now include those boundaries; all tracks pass.

## 2026-07-20 - Bind nondeterministic parameter IDs safely

The first hosted run proved that parameter display IDs containing import-time
UUID values are not stable across preflight and shard processes. Raw preflight
node IDs are therefore not executable cross-process authority. Shards execute
validated whole modules, record final collection and completion in the same
pytest process, require those exact sets to match, and bind their stable
test-base cardinalities to the authenticated preflight manifest.

## 2026-07-22 - Split reset safety from semantic-lane topology

PR #180 is discovery and an immutable contributor source, not authorized
implementation. Review showed its destructive migrate-once reset and its CI
lane/workflow rewrite cross separable L1/P0 boundaries. Chunk 02A must first
prove runner-owned reset containment, canonical trigger restoration, migration
state, and fixture equivalence under the existing CI topology. Only later chunk
02B may replace that topology, with independent exact-node validation and
isolated PostgreSQL and MinIO custody. This limits rollback and review scope
while preserving Konan's authorship.

## 2026-07-22 - Defer routing, dependency cache, and durable timing weights

Measured evidence shows repeated migrations and service-heavy execution are the
current bottleneck. Path routing, dependency caching, sampling, and durable
timing weights add invalidation and silent-suppression risk without addressing
that cause. Chunk 02 therefore makes a reviewed no-implementation decision for
those original options. They may be reassessed only in future planning chunk
`WS-CI-001-03`, after 02B exact-head evidence exists; 03 is not a successor of
this PR and has no start authority.

## 2026-08-03 - Restore real hosted parallelism

Exact GitHub evidence shows migrate-once semantic lanes remain correct but take
15m31s when four subprocesses compete on one hosted runner. Keep semantic lane
ownership and exact custody, but execute each lane in an independent matrix job
and combine only authenticated evidence in the stable final `test` job. Remove
review-event reruns because review state does not change the tested commit.
