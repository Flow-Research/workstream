# Intent: WS-QUAL-001 Backend Coverage Floor

## Human goal

Maintain at least 90 percent statement coverage for the complete backend
application and make CI fail below that floor.

## Success state

- CI runs the complete backend suite with `pytest-cov` and a configured
  `fail_under` of at least 90 percent.
- Coverage includes all importable modules under `backend/app`; application
  modules are not omitted and lines are not suppressed to manufacture a pass.
- Tests exercise meaningful success, rejection, failure, and recovery behavior.
- Database-backed verification uses an isolated database per worktree or CI job.
- The full suite passes at or above 90 percent on the exact reviewed tree.

## Non-goals

- No production behavior, public API, schema, migration, or authorization change.
- No deletion of valid code solely to improve the percentage.
- No mock-only assertions that merely execute lines without checking outcomes.
- No weakening of lint, docstring, API drill, or existing test gates.

## Human direction

The user first requested 80 percent, then corrected the authoritative minimum
to 90 percent on 2026-07-11.
