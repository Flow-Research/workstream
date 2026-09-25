# Behavior proof instead of coverage quotas

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: percentage coverage no longer gates contributions; full behavior verification remains blocking, with redundant coverage-only execution removed.

## Intent

The human explicitly retires mandatory test-coverage percentages. Thousands of
passing tests and high coverage did not prevent defects found by real API drills.
Tests must protect meaningful behavior rather than satisfy line-count quotas.
Before this change, the Backend workflow had global, subsystem and per-file
floors plus four extra focused executions after the complete semantic lanes.
MCP also had a percentage floor. AGENTS.md and CONTRIBUTING.md required them.

## Bounded change

Allowed: Backend/MCP test workflows, their test runners and integrity tests,
affected test-only redundant or retired-policy cases, AGENTS.md, CONTRIBUTING.md,
PR guidance, the affected review skills and current engineering/roadmap documentation. Audit existing test
consumers before removing cases and record the retained behavioral proof below.
Existing shared syntax/skip detection remains even if its old coverage-policy
consumer is retired. Historical records are not rewritten.

Not allowed: product behavior, data/migrations, authorization or architecture
changes; skipping failures, replacing real PostgreSQL/S3 with mocks, reducing
full-suite selection, weakening rollback/concurrency checks, removing a unique
regression merely because its test looks long, or adding a new scoring gate.

## Design and decisions

Remove percentage pass/fail checks and duplicate coverage-focused reruns, after
proving those tests remain in the complete lane catalogue. Retain aggregate
coverage as diagnostic telemetry during this bounded change, not a quality
quota. Preserve evidence integrity and infrastructure cleanup independently of
the measured percentage. Keep end-to-end drills and focused boundary tests;
end-to-end-only testing cannot economically prove every race or failure branch.

Test deletion requires a concrete reason: superseded requirement, identical
proof already retained at the correct boundary, or an assertion about incidental
implementation with no required observable behavior. Test count is not a goal.
No unreviewed repository-wide purge. Record candidates not yet safely removable.

## Acceptance criteria

- No Backend or MCP percentage threshold can fail CI or require new tests.
- Full collected suite, real API drill, PostgreSQL/S3, failure propagation,
  exact-head completeness and isolation/cleanup checks remain blocking.
- Removed duplicate reruns have complete retained lane ownership.
- Removed test cases have an explicit deletion reason and retained proof where
  the behavior remains required; no unique negative-path proof is lost.
- Contributor instructions require risk-based behavior tests and live-drill
  regression cases, not percentages or a mandatory test count.

## Risk and review routing

- Risk class: L1 (explicitly authorized CI policy change).
- Required reviewers: CI integrity, QA/test delta, documentation; architecture
  only if shared tooling ownership changes.
- Human review focus: retirement of coverage quotas is intentional; correctness,
  real integration checks and test completeness are not retired.

## Evidence

Run workflow integrity, lane catalogue and affected tooling tests locally;
Markdown/stale scans and Commitrail checks; full hosted Backend and MCP workflows
on the final PR head. Review each deleted test against its remaining owner.
Assess roadmap engineering quality language without claiming new product work.

### Deletion/redundancy accounting

- Four redundant reruns: POL-04A2 finalization, project authorization-read
  composition, sufficiency mutations, and submission-policy mutations. All
  selected modules remain in `PROJECT_MODULES` and execute in project lanes;
  their PostgreSQL variants remain there too. No product cases removed.
- Five workflow snapshot tests only enforced retired percentage floors or
  repeated commands. Replaced by diagnostic-only and retained-family membership
  proof in `test_ci_lane_catalogue.py`; exact recursive catalogue/collection,
  workflow lane inventory and failure/cleanup tests remain.
- Retired `coverage_policy.py` percentage/configuration/evidence/CLI and unused
  delta/rename helpers had no live consumer outside their own tests. Remove
  those dead functions and their cases; retain the shared `SyntaxPolicy`,
  `analyze_python`, `weak_python`, lexical regression matrix and type-variable
  traversal tests used by `test_structure_boundary.py`. Keep the real SQLAlchemy
  tracing regression because diagnostic accuracy remains useful.
- Preserve docstring checks (not test-coverage quotas), coverage dependencies and
  raw artifact digests, full eight-lane execution, API drill, MCP lint/typecheck,
  packaging/container/real-API checks, and PostgreSQL/S3 cleanup proof.
- Inline hosted evidence validation now accepts the entire finite 0..100 range;
  low percentages cannot fail it. Missing/corrupt execution evidence still fails.
- Remove five direct `weak_python` duplicate cases from the architecture suite;
  its 82-case lexical owner matrix covers these same framework mechanisms.
  Architecture path-selection/integration tests remain. Total retirement is
  94 existing cases (89 obsolete quota/dead-policy cases and five duplicates),
  replaced by two small diagnostic/completeness contracts: net 92 fewer cases.
  This is a bounded audit, not a claim that every remaining product test is necessary.
