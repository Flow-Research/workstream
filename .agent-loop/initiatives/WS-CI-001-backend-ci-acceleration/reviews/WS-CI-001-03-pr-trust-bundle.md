# WS-CI-001-03 PR Trust Bundle

## Intent

Correct a backend CI regression where four semantic processes compete on one
hosted runner for 15m31s and the complete Backend workflow repeats when review
state changes.

## Design

- Run semantic ownership on five independent matrix runners, including two
  deterministic exact-node partitions for `test_alembic.py`.
- Upload one exact checked-out-tree bundle per lane using an explicit file list.
- Keep `Backend / test` as the stable, always-run final required check.
- Reject upstream failure before fan-in; reconcile exact manifests, nodes,
  resource isolation, and byte digests before combining coverage once.
- Run the existing API E2E against live PostgreSQL and pinned MinIO.
- Move the exceptional guide-dependency approval refresh to required, fast
  Agent Gates instead of rerunning Backend on every review event.
- Cancel superseded Backend runs for the same PR.

## Integrity preserved

- No test is skipped, removed, sampled, deselected, or weakened.
- Global 78 percent and every protected 90 percent coverage floor remain
  blocking.
- Real migrations, PostgreSQL constraints/locks/triggers/concurrency, MinIO,
  and API contract proof remain in required CI.
- Matrix databases, roles, MinIO namespaces, coverage files, and artifacts are
  isolated per lane.
- Missing, failed, cancelled, foreign, duplicate, symlinked, traversing,
  digest-mismatched, or incomplete evidence fails closed.
- Workflow permissions remain read-only.

## Evidence

- Prior successful baseline: run `30782031524`, job `91588477886`, 17m20s total,
  15m31s in the four-lane single-runner step.
- First distributed run `30786185424` proved real parallel execution; schema
  job `91600051005` took 13m09s, including 707.60 seconds for 105 tests in
  `test_alembic.py`. The final job then exposed the corrected module-invocation
  defect before coverage fan-in.
- Local deterministic checks: 77 focused tests and seven workflow regression
  tests passed; Ruff, YAML parse, links, stale wording, and diff checks passed.
- All focused internal review tracks pass after repairs.

## Human review focus

1. Confirm five matrix jobs represent the intended runner cost/latency tradeoff.
2. Confirm `Backend / test` and `Agent Gates / agent-gates` remain the required
   branch-protection contexts.
3. Inspect exact PR run timing and ensure complete Backend wall time approaches
   or beats the eight-minute target.
4. Confirm CodeRabbit and GitHub checks are green on the final commit.

The user retains the merge decision. Local timing is not acceptance evidence.
