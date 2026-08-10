# WS-POL-003-03A External Review Response

## Comments addressed

- All five substantive CodeRabbit threads were validated and corrected:
  compilation attempt states are subsystem-specific; repository failures expose
  one domain hierarchy with a retryable lineage-race subtype; the canonical
  execute digest has explicit behavior ownership; deny-only coroutines are
  created inside their assertion scopes; and local PostgreSQL uses CI's exact
  image digest.
- Valid review-body findings were also corrected: explicit public-fact test
  construction, canonical-result equality, shared component-hash constraint
  composition, full-result-hash coverage, fresh ORM reloads, fixed-service
  narrowing, migration cleanup safety and schema-scoped trigger inspection,
  and application/database terminal-code parity.
- Initial exact-head GitHub backend lanes all stopped at the shared docstring
  gate before test execution. The nine new repository callables and six
  deny-only authorization methods now document their exact responsibilities;
  repository-wide docstring coverage is 80.4 percent, above the unchanged 80
  percent docstring gate. This is distinct from the 78 percent repository test
  coverage floor.
- On the corrected head, four semantic lanes passed. `schema_contracts_a`
  exposed a stale 0049 round-trip assertion: it stripped only 0049 action
  tokens before comparing the current head to 0048. The assertion now also
  strips 0062's exact, independently tested compilation action token. Migration
  behavior and database guards are unchanged.
- The first assertion-fix head was rejected by the zero-growth preflight because
  it expanded the already oversized historical migration test. The correction
  was reformatted to shrink that file from 14,096 to 14,093 lines; the debt
  ledger records only that exact shrink and new content hash. CI-integrity
  re-review and canonical structure validation pass with no exception or new
  debt.

## Comments deferred

- The suggested `NOT VALID` rewrite for the three `audit_events` constraints was
  not applied. Migration 0062 deliberately locks and rewrites all three closed
  registries in one transaction so no observer can see a partial catalogue.
  PostgreSQL retains the `ACCESS EXCLUSIVE` lock until that transaction commits,
  so adding and validating `NOT VALID` constraints inside the same transaction
  would not shorten the lock and would weaken the single atomic registry change.
- Test-only fixture consolidation suggestions are recorded as non-functional
  cleanup, not mixed into this security correction; every affected test retains
  explicit engine cleanup and focused behavior ownership.
- The request to express internal engineering reviewer results as
  `accept`/`needs_revision`/`reject` was not applied. Those values are reserved
  for Workstream product review decisions; engineering review evidence remains
  pass/fail with residual risk recorded separately, as required by `AGENTS.md`.

## Human decisions needed

- None for this correction. Human merge approval remains required after all
  exact-head checks and external review complete.

## Commands rerun

- Scoped Ruff for both corrected modules.
- Repository `docstr-coverage --config .docstr.yaml`.
- Test-structure validation and diff integrity.
- Focused 0062 migration-contract tests: 2 passed against PostgreSQL.
- Final isolated guide-compilation suite: 31 passed with 93.08 percent package
  coverage against the unchanged 90 percent floor.
- Structure, behavior-ownership, and lane-inventory regression bundle: 161
  passed.
- Test-delta re-review: pass; the historical assertion still requires both the
  0049 and 0062 additions exactly twice and rejects all other definition drift.
- Hosted schema lane on the corrected head.

## Remaining risks

- GitHub must rerun every backend lane and coverage gate on the corrected head.
- CodeRabbit must receive the corrective head and every resolved thread must be
  verified through the thread-aware API before merge readiness.
