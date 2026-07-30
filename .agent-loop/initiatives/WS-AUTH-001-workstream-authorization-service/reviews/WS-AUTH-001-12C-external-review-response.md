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
- Hosted Backend and exact-head CodeRabbit reruns are pending the corrective
  commit.

## Remaining risks

Hosted full-suite execution and exact per-file coverage remain authoritative.
