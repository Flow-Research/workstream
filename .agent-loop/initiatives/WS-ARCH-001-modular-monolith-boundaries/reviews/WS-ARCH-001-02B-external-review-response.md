# WS-ARCH-001-02B External Review Response

## Comments addressed

- Replaced the stale AUTH-only transition-validator wording with the exact
  module public-API foundation terminology.
- Extracted exact historical-lineage resolution from the legacy 1,300-line
  PROJECT repository into `ProjectLockedPolicyRepository` and added that
  bounded module to the chunk's 90 percent coverage command.
- Replaced iteration-count PostgreSQL lock polling with a wall-clock deadline
  and a bounded positive polling interval.

## Comments deferred

None.

## Human decisions needed

None beyond the existing PR review and merge decision.

## Commands rerun

- Ruff formatting and lint for the affected PROJECT and CI files.
- Focused PROJECT boundary and locked-policy tests with coverage for
  `app.modules.projects.api` and
  `app.modules.projects.locked_policy_repository`.
- Module-boundary, behavior-ownership, and test-structure validators.
- Markdown-link and whitespace checks.

## Remaining risks

PostgreSQL-backed cases remain delegated to the hosted `project_lifecycle`
lane because no local test database URL is configured.
