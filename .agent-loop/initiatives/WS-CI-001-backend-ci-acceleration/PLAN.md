# PLAN: WS-CI-001 - Backend CI Acceleration

## Objective

Reduce Backend workflow wall-clock time while preserving complete test execution,
real service integration, exact-head provenance, and every current coverage and
branch-protection gate.

## Proposed approach

### 1. Deterministic inventory and partitioning

Add a repository-owned planner with one shared validation implementation.
Canonical module completeness comes from symlink-safe filesystem discovery of
`backend/tests/test_*.py`, with an explicit declaration excluding only
`test_isolated_database_runner.py`. A successful pytest collection supplies the
canonical per-test-base cardinality signatures and per-module weights; every node must map to one
discovered canonical module. Collection errors, zero-test modules, foreign paths,
malformed node IDs, and parameterized-node collisions fail.

Assign every non-excluded module exactly once using deterministic
largest-weight-first bin packing with lexical tie-breaking. Emit canonical,
schema-versioned JSON binding schema, actual checked-out tree SHA from
`git rev-parse HEAD`, ordered normalized module paths, explicit exclusion,
ordered stable node signatures, collected counts, shard count, weights, and assignments. Its
SHA-256 digest identifies the exact executable inventory and plan.

The initial weight is collected test count per module. Runtime telemetry may
replace or augment weights only in the later optional chunk after its provenance
and stability are reviewed.

### 2. Fast prerequisite job

Retain evidence, install, lint, docstring, isolated-runner self-test, collection,
and shard-plan validation ahead of the expensive matrix. Upload the immutable
manifest for the current commit. A collection or planning failure prevents all
shards.

### 3. Isolated parallel shards

Run four matrix jobs initially. Each validates its actual checked-out tree SHA
against the manifest, provisions its own PostgreSQL service and independently
owned migrated database through `run_isolated_tests.py`, starts MinIO, and runs
only manifest modules through Python argv/subprocess construction rather than
shell-expanded module strings. It executes the manifest's validated whole-module
paths and uses repository-owned pytest hooks to record final collection and
runtime completion in that same pytest process. It requires those exact runtime
sets to match and their stable test-base cardinalities to match preflight, writes
a unique coverage file, and uploads a fixed-name bundle containing shard ID,
tree SHA, manifest digest, collected/completed node IDs and counts,
allowlisted non-secret metadata, coverage, and SHA-256 of the coverage bytes.

No shard shares a database, role, filesystem artifact, or coverage filename.
No test is selected by an untrusted PR-provided shell fragment.

### 4. Concurrent API contract proof

Run the existing real API contract E2E command as a separate dependent job after
fast prerequisites and concurrently with shards. Preserve its isolated database
and timeout behavior.

### 5. Fail-closed final fan-in

Keep workflow name `Backend` and final job ID `test`, preserving the existing
`Backend / test` required-check context. Other jobs use different IDs. Run the
final job after every shard and API proof with `if: always()`. It must reject any
failed, cancelled, or skipped prerequisite; missing/extra shard; tree-SHA or
manifest-digest mismatch; malformed metadata; duplicate/omitted module or node;
collection-count mismatch; missing coverage; coverage-digest mismatch; symlink,
path traversal, non-regular file, or unexpected path. It accepts exactly four
fixed artifact names containing tree SHA and shard ID, downloads without wildcard
surplus, and recomputes canonical bindings rather than trusting repeated labels.

Only after provenance validation does it combine coverage data and enforce the
unchanged repository-wide and twelve protected coverage reports. The final job
uploads concise timing and shard-balance evidence.

### 6. Evidence and rollout

Test the planner and fan-in validator locally, including a real repository
collection-to-plan-to-four-shard-selection-to-fan-in dry run. Statically test the
workflow in the agent-gate suite and run the implementation PR on GitHub. Compare hosted
wall time and shard distribution with the PR #161 baseline. Do not claim a
latency target passed until exact hosted evidence exists.

Matrix job state supplies visible progress; final shard duration/balance metadata
supplies timing evidence. Live pytest output is not required because the
unchanged isolated runner intentionally buffers and redacts child output.

## Alternatives rejected

- Test or coverage sampling.
- Path-based Backend skipping in the first chunk.
- Shared-database xdist processes.
- Unpinned marketplace sharding actions.
- Mutable external timing data without commit/inventory provenance.
- Allowing the aggregator to pass when an upstream job is skipped or cancelled.

## Architecture and security boundaries

- Planning and execution logic remain CI-only under backend scripts and GitHub
  workflows; product modules are not imported as orchestration services.
- Planner input is treated as data and emitted module paths are validated before
  command construction.
- Artifacts are accepted only for the actual checked-out tree and expected
  canonical manifest digest, and coverage bytes are independently hashed.
- Top-level and job permissions explicitly set `contents: read` plus only minimum
  run-scoped artifact access; no repository write exists and
  `pull_request_target` is prohibited.
- No database URL/password, MinIO credential, environment dump, or runner
  database metadata outside an allowlisted non-secret schema enters artifacts.

## Verification strategy

- Planner tests: filesystem/node completeness, parameterized nodes, zero-test and
  collection failure, determinism, exact-once assignment, stable ties,
  empty/malformed rejection, traversal/symlink rejection, shard bounds, and
  canonical manifest-digest binding.
- Fan-in tests: missing, duplicate, extra, foreign-SHA, foreign-digest, malformed,
  failed, cancelled, skipped, missing/duplicate/foreign node, count mismatch,
  coverage-byte mismatch, symlink, traversal, unexpected-file, and coverage-file
  mismatch rejection.
- Workflow tests: immutable action pins, fixed matrix size, isolated database per
  job, no shared coverage path, explicit failure propagation, stable final check,
  unchanged coverage floors, and no path-based skip.
- Existing runner, agent-gate, backend, coverage, and API E2E tests.
- Hosted exact-checked-out-tree timing report against PR #161.

## Operator documentation

Update canonical `docs/operations_backend_testing.md` with preflight, shard, API,
and fan-in diagnosis; fixed artifact contents and retention; whole-workflow versus
failed-job reruns and stale rejection; parallel runner cost; stable check identity;
progress semantics; and one-PR rollback.

## Rollback

If hosted sharding is unstable or slower, revert the implementation PR as one
workflow/script unit to restore the existing sequential job. Do not lower
thresholds, disable shards, or silently fall back inside the workflow.

## Delivery order

1. `WS-CI-001-01`: deterministic parallel full-suite execution and centralized
   coverage fan-in.
2. `WS-CI-001-02`: optional measured routing/cache/telemetry improvements after
   01 has stable hosted evidence.

Implementation does not begin until the reviewed 01 contract receives explicit
human approval.
