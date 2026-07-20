# External Review Response: WS-CI-001-01R1

## Comments addressed

- CodeRabbit major stability finding on PR #163: the isolated child-runner
  timeout exceeded its enclosing GitHub job timeout for both shard execution
  and API E2E.
- Shard child timeout is now 4,800 seconds inside a 90-minute job, preserving a
  10-minute configured budget gap and operational cleanup headroom.
- API E2E child timeout is now 1,500 seconds inside a 30-minute job, preserving
  a 5-minute configured budget gap and operational cleanup headroom.
- Workflow regression tests assert both child timeouts remain below their job
  budgets.

## Comments deferred

None.

## Human decisions needed

None. The finding is a clear in-scope cleanup and failure-propagation defect.

## Commands rerun

- Ruff formatting and lint: passed.
- Shard and coverage-contract tests: 204 passed.
- Isolated database runner against local PostgreSQL: 16 passed.
- Agent-gate workflow tests: 91 passed.
- Markdown links, stale wording, loop-memory state, and diff integrity: passed.
- Required internal review: all nine tracks passed the rebased repair; senior,
  architecture, docs, and reuse/dedup then confirmed the chunk-map repair.

## Remaining risks

GitHub may still terminate a runner for infrastructure reasons, but configured
test timeouts now leave operational headroom for the repository-owned isolation
runner to terminate its child and drop its exact owned database and role. The
configured gaps are not guarantees because job setup also consumes wall time.
