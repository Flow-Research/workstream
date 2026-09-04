# Discovery: WS-QUAL-002 Behavior Ownership Catalogue

## Repository facts

- Eligibility is defined by `ELIGIBLE_PREFIXES` in
  `backend/scripts/mutation_policy.py`.
- Exact changed callables are derived by `changed_callables()` using Git
  merge-base hunks and AST spans.
- `build_selection()` currently requires changed targets and claimed callables
  to match exactly.
- Claim schema v1 is in `scripts/behavior-claim.schema.json`; it permits at most
  eight targets, 24 callables per target, and 12 exact pytest nodes per target.
- Backend semantic ownership is process-level, not production ownership:
  `backend/scripts/run_test_lanes.py` assigns all 66 test modules to five lanes.
- The current hosted Backend run proves all lane nodes and combines coverage,
  but it does not emit callable-to-test context ownership.

## Scope inventory

- 168 eligible implementation/script modules excluding `__init__.py`.
- 66 top-level backend test modules.
- High-risk groups include authorization/actors/auth, artifacts/storage,
  projects/tasks/checkers/reviews, audit/outbox, async job runtimes, and CI scripts.
- Existing behavior claims cover mutation-policy calibration only; they are not
  a repository ownership catalogue.

## Existing evidence that can be reused

- Exact AST callable mapping in `mutation_policy.py`.
- Exact test collection and lane custody in `run_test_lanes.py`.
- Combined coverage and protected subsystem floors in `coverage_policy.py` and
  the Backend workflow.
- Current schema vocabulary for outcomes and real boundaries.
- `pytest-cov`/coverage support test contexts, which can provide candidate
  callable-to-test evidence without inventing ownership from imports.

## Gaps

- No canonical target/callable ownership registry.
- No deterministic command to prepare ownership before implementation.
- No context-coverage artifact mapping executed lines to exact pytest nodes.
- No completeness check covering every eligible module.
- No stale-node check proving catalogue tests still collect.
- No bounded rule for modules whose owning test would exceed mutation runtime.

## Dependencies and integrations

The solution touches mutation policy, test collection/coverage evidence,
repository schemas, contributor documentation, and the mutation workflow. It
must use protected-base authority and cannot trust PR-head catalogue changes
without validation.

## Risks

- Static import inference can overclaim behavior ownership.
- Coverage contexts show execution, not assertion strength; mutation remains
  the assertion-sensitivity proof.
- A single test module can be too broad for bounded mutation.
- Catalogue population is data-heavy and must be split by subsystem.
- Renames/deletions require explicit fail-closed catalogue reconciliation.

## Unknowns to resolve during the prototype

- Hosted size/runtime cost of per-test coverage contexts.
- Whether exact test functions or stable test groups are the best stored unit.
- How many eligible modules contain no executable callable and should be typed
  `structural_only` rather than mutation-owned.
- Which existing broad integration tests need smaller owning behavior tests.
