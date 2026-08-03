# WS-ART-001-03C External Review Response

## Comments addressed

- Agent Gates initially rejected restricted human/worker vocabulary in the
  README Celery Beat note. The note now uses execution-process terminology;
  the stale authorization documentation check passes and the rerun succeeded.
- Backend semantic lanes exposed project/task fixtures that assumed setup runs
  existed even when test configuration disabled autostart. Verified fixtures
  now create one production-shaped generation run only when absent, isolated
  worker tests explicitly create their run, and downstream task fixtures bind
  the verified report to that same run.
- The queued-before-verified-material assertion now uses the persisted
  `current_step="queued"` contract.
- Backend run `30781770775` then exposed eight remaining project-lifecycle
  fixtures that still selected diagnostic reports or omitted verified-report
  setup-run linkage. Those fixtures now use exact verified reports, and the
  policy-derivation route composes the canonical verified-material adapter.
- CodeRabbit inline findings were verified and resolved: migration constraint
  operations use the physical PostgreSQL name in both directions, guide
  continuation recovery publishes the continuation directly with an
  independent bound, and the two documentation claims now match implementation.

## Comments deferred

- None.

## Human decisions needed

- None. Human merge approval remains required after hosted checks pass.

## Commands rerun

- Ruff over backend application, tests, backend scripts, and repository scripts.
- Python compilation for backend application and tests.
- Stale authorization and artifact documentation checks.
- Lightweight agent gates and Markdown link validation.

## Required next evidence

- Hosted Backend and Agent Gates rerun after this repair is pushed.

## Remaining risks

- The database-backed fixture repairs require the next hosted Backend semantic
  lane run because no local test database URL is configured.
- CodeRabbit's latest incremental review reported no new actionable findings;
  all earlier inline findings were checked against the final diff.
