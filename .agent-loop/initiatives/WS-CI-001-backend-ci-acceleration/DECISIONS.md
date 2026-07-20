# DECISIONS: WS-CI-001 - Backend CI Acceleration

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
