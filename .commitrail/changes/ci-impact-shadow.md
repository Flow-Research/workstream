# Backend test-impact shadow trial

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: report conservative test-module impact candidates without changing full backend CI execution.

## Intent

Every backend run executes the complete semantic-lane catalogue. Before considering
selective execution, learn whether repository-native dependency information gives
useful candidates. This is an experiment, not evidence that omitted tests are safe.

## Bounded change

Allowed: a backend impact-report script and focused tests, registration in the
existing test catalogue, an advisory step in `.github/workflows/backend.yml`,
the exact behavior-ownership partition and validator registration, the testing operations guide
and this record. No product code, dependencies,
permissions, required gates, lane selection, pytest invocation, coverage policy,
or retry-artifact behavior changes.

## Design

Reuse the canonical Git delta helpers, module registry, static import reader and
test catalogue. For changed module Python files, compute reverse transitive
module dependencies and candidate test modules. Include changed test modules.
Treat uncertain imports/test ownership, shared fixtures, application composition,
AUTH, migrations, dependencies, deletions, and unclassified paths conservatively:
recommend the full suite with explicit reasons. Deduplicate partitioned lanes.
Bind the report to the exact checked-out Git head, base and merge base. Parse
source only; never import application or test modules to discover dependencies.

The existing preflight logs JSON in a report-only step.
Errors remain visible but cannot bypass or replace any required check. All seven
lanes and coverage aggregation run exactly as before. No hosted service, stored
test-history system or selective execution is introduced. The first trial measures
candidate module counts and fallback causes, not runtime savings or demonstrated
false-negative rates. Those require subsequent evidence and a separate decision.

## Acceptance criteria

- Direct and transitive consumers appear; unrelated owners are not silently
  treated as dependents. Cycles terminate and partitioned modules deduplicate.
- Unknown/shared/deleted paths, unresolved ownership and unsafe source analysis
  recommend all catalogue modules. Git target errors do not emit a success claim.
- Focused tests exercise a temporary real Git repository and import fixtures;
  a defective missing-transitive-edge variant must fail its named regression.
- Run focused pytest, Ruff, catalogue inventory, Commitrail, links/stale checks,
  and the complete hosted Backend workflow. Confirm no existing check is relaxed.

## Risk and review routing

L1 (CI). Plan review before implementation. Frozen implementation: CI integrity
and documentation; QA/test delta and reuse/architecture for the dependency
analysis. Human focus: the report cannot authorize omission of tests.

## Reconciliation

PR #408 retry selection is preserved. Product roadmap impact: none; no capability,
exposure or product dependency changes. Remaining boundary: evaluate report
usefulness before proposing selective execution. Do not claim this trial speeds CI.

Plan review clarified that mandatory process records and dynamic source analysis
may produce full-suite recommendations on every current run. Keep known-edge
candidates separate from recommended execution. Include private as well as public
static imports; the architecture validator's public-only graph is insufficient.

## Evidence

Focused reporter and lane-catalogue tests pass (54 cases); the earlier 53-case
coverage run measured reporter coverage at 98.98 percent. A missing-transitive-edge mutation is rejected by
`test_reverse_transitive_private_and_public_consumers`. Real temporary Git tests
cover exact target binding, deletion visibility and dirty-checkout rejection.
Hosted integration and exact-head reviewer freshness are recorded in the PR.
