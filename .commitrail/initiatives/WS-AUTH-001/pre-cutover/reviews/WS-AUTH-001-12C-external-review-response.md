# WS-AUTH-001-12C external review response

## Comments addressed

- Made migration constraint naming convention-safe and every custody comparison
  NULL-safe; also require a bounded SHA-256 resource-context digest.
- Made concurrent same-key reservation acquisition block on and return the
  winning row through a guarded no-op upsert instead of racing an invisible row.
- Added portable asyncpg/direct/psycopg constraint-name extraction for slug
  conflicts.
- Corrected fixture authority side effects, count-sensitive assertions, UUID
  validation, test ownership, indentation, pending-row coverage, and missing
  constraint inspection.
- Removed dead test branches, deduplicated project-create binding comparison,
  and included audit schemas in the chunk verification commands.

## Comments deferred

- Returning a session-managed ORM object from a pre-0044 schema was not adopted:
  the current ORM mapping selects columns absent from that historical schema.
  The helper now returns no object; every caller uses it only for persistence.
- Removing the existing-grant lookup was not adopted because the latest shared
  helper is also used for admitted API actors, where grant reuse is reachable.
- An evidence opt-out was not adopted because an attributed project without its
  allowed authorization event would violate the 0044 custody contract. Tests
  now compare scoped baselines or correct authority totals instead.

## Human decisions needed

None.

## Commands rerun

- Focused Ruff and `git diff --check`: passed.
- AUTH-12C PostgreSQL lane: 12 passed.
- Migration downgrade plus concurrent replay/slug rollback: 3 passed.
- Count-sensitive auth/audit checks: 3 passed; the initially failing artifact
  baseline check was corrected and then passed with task/checker regressions.
- Task/checker/artifact fixture regressions: 3 passed.
- Three project-lifecycle regressions exposed by the hosted lane were corrected
  by revoking fixture-only system Project Manager authority before exercising
  narrower grant and revocation semantics: 3 passed.
- The 0044 unattributed-project proof now observes the intentionally deferred
  custody constraint at transaction commit instead of only at statement
  execution: 1 passed.
- The next hosted run exposed shared fixtures manufacturing new project-create
  evidence for projects that semantically predate 0044. Shared fixtures now
  seed explicit historical projects without queued custody events; the one 0044
  downgrade-custody test retains the fully attributed fixture. Seven artifact
  authority regressions and four historical downgrade regressions passed.
- Updated three stale AUTH test doubles to the resource-context-aware decision
  staging signature and proved prepared-dependency denial evidence persists
  through its owned rollback/restage/commit path: 3 passed.
- The following hosted run reduced shared-foundation failures to one auth
  lifecycle test whose two exact grant totals still included the removed
  fixture-only grants. The totals now assert the three real grants at that
  lifecycle point, and the complete affected test passes.
- The next hosted run passed project and task lanes and exposed the remaining
  direct unattributed project insert in the shared outbox fixture. It now uses
  the same explicit historical-project helper; all 72 outbox tests pass.
- The subsequent hosted run passed shared, project, and task lanes. Its three
  schema-contract failures were the last direct project inserts inside
  migration helpers. A caller-transaction variant of the historical helper now
  preserves normal setup transactions, while the outbox race commits historical
  setup before opening its writer transaction; all three exact schema tests pass.
- The exact-head rerun passed all four semantic lanes, Agent Gates, and
  CodeRabbit. Its per-file cutover gate then reported 87.41 percent for the
  prepared dependency composition root. The existing lifecycle test now proves
  rollback of a forgotten successful transaction and fail-closed denial-evidence
  persistence, covering the four lines required to reach at least 90 percent.
- The next exact-tree retry passed lane custody and measured the composition root
  at 90.37 percent. It then exposed that the gate also covered the broad legacy
  project repository at 62.46 percent. Project-create reservation/completion now
  has a dedicated repository boundary, restoring the legacy repository to its
  prior scope; focused branch tests measure the new module at 96.43 percent.
- The following hosted run passed the dedicated repository at 96.43 percent and
  exposed the same whole-file mismatch for the broad legacy project router at
  58.96 percent. The route and orchestration now join persistence in focused
  project-create modules; legacy router/service diffs only remove their obsolete
  token-role create path. Sixteen focused PostgreSQL integration tests pass after
  the split. Twenty-two focused unit tests also pass, with exact boundary
  coverage of 100 percent for the shared database-error helper, 96.43 percent
  for the repository, 100 percent for the router, and 94.12 percent for the
  service.
- A final hosted Backend rerun is pending this complete boundary correction;
  CodeRabbit must also review that exact head.
- Exact-head CodeRabbit review then identified one valid deduplication nit: the
  supported-driver constraint-name lookup existed in both project creation and
  project-role mutation. A shared database-error helper now owns that lookup;
  both callers retain their existing constraint allowlists and re-raise behavior.

## Remaining risks

Hosted full-suite execution and exact per-file coverage remain authoritative.
