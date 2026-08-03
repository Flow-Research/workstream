# Intent: WS-QUAL-001 Backend Coverage Floor

## Human goal

Make the complete backend test suite protect at least 90 percent statement
coverage without weakening tests, hiding application files, or making CI slow
through unnecessary PostgreSQL and HTTP duplication.

## Why this matters

Coverage is a backstop for behavior proof, not the goal by itself. Workstream's
authorization, artifact, project, task, checker, review, and contribution
boundaries need meaningful failure and recovery tests while the repository
remains practical for contributors.

## Current truth

The latest complete hosted result before this reconciliation ran 2,914 tests
and covered 20,787 of 23,368 application statements: 88.954981 percent. The
global CI floor remains 78 percent, while named new or materially changed
subsystems are already protected at 90 percent.

## Success state

- The exact complete backend suite covers at least 90.00 percent globally
  across the complete importable `backend/app` inventory.
- GitHub CI blocks below a global `--fail-under=90` floor.
- New tests protect observable behavior, rejection, failure, or recovery.
- Pure or adapter-contract tests are preferred when PostgreSQL and HTTP are not
  the behavior under test.
- Existing semantic lanes, isolation, coverage combination, and protected
  90-percent subsystem checks remain intact.

## Non-goals

- No production behavior, schema, migration, API, authorization, or product
  lifecycle change.
- No arbitrary sharding or infrastructure purchase.
- No test deletion, weakened assertion, skip, xfail, coverage pragma, omit, or
  narrowed application inventory.
- No revival of the historical signed-memory, base-evidence, semantic-parser,
  line-budget, or per-milestone ratchet process.
- No promise that coverage alone proves correctness.

## Human decision already provided

The user directed the orchestrator to restart QUAL only after current-main
documentation reconciliation. This PLAN2 audit is authorized; implementation
still begins with the first reviewed bounded successor.
