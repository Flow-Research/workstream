# WS-CI-001-01 Preimplementation Plan Review

Reviewed scope: `INTENT.md`, `DISCOVERY.md`, `PLAN.md`, `CHUNK_MAP.md`,
`STATUS.md`, `RISKS.md`, `DECISIONS.md`, and chunk contracts 01 and 02.

Risk route:

- Risk class: L1
- SLA: P1
- Work type: CI, infrastructure, test, architecture, documentation
- Human gate: explicit approval before implementation and before PR merge
- Budget posture: proof-heavy; latency improvement cannot weaken test evidence

## Final results

| Track | Result | Blocking findings |
|---|---|---|
| Senior engineering | PASS | None |
| QA/test | PASS | None |
| Security/auth | PASS | None |
| Product/ops | PASS | None |
| Architecture | PASS | None |
| CI integrity | PASS | None |
| Docs | PASS | None |
| Reuse/dedup | PASS | None |
| Test delta | PASS | None |

Reviewer runs:

- senior engineering, architecture, reuse/dedup: `ci_plan_arch`
- QA/test, CI integrity, test delta: `ci_plan_qa`
- security/auth, product/ops, docs: `ci_plan_sec_ops`

## Findings repaired

- Grounded module completeness in symlink-safe filesystem discovery and bound
  executable completeness to canonical collected pytest node IDs.
- Required each shard to report observed nodes and fan-in to prove their exact
  union equals the prerequisite inventory once, including parameterized nodes.
- Defined canonical manifest serialization over schema, actual checked-out tree,
  exclusions, ordered modules/nodes/counts, weights, assignments, and shard count.
- Required exactly four fixed artifacts, SHA-256 coverage-byte binding, allowlisted
  regular files, and rejection of surplus, symlinked, traversing, malformed,
  colliding, foreign, or secret-bearing content.
- Preserved workflow `Backend`, final job ID `test`, and required context
  `Backend / test`; required `if: always()` plus explicit dependency-result checks.
- Required Python argv invocation, read-only permissions, no
  `pull_request_target`, and a digest-pinned PostgreSQL image.
- Reused `run_isolated_tests.py` for database ownership and
  `docs/operations_backend_testing.md` for operator guidance.
- Added isolation/coverage regression commands and a real
  collection-to-plan-to-four-shard-to-fan-in local dry run.

## Final assessment

`WS-CI-001-01` is cohesive because inventory, isolated execution, evidence
fan-in, and centralized coverage form one indivisible CI trust boundary. Splitting
them into separate implementation PRs would leave an unsafe intermediate state.
The plan preserves every test and coverage threshold and is ready for explicit
human implementation approval. `WS-CI-001-02` and `WS-ENG-001-04B` remain
inactive.
