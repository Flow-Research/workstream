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
- Backend run `30783400382` reduced the remaining failures to five exact test
  seams: warning tests now acknowledge the diagnostic record used by manual
  policy creation and the verified record used by activation; direct service
  tests compose the verified-material adapter. It also exposed that the worker
  used traceback logging for an unexpected parser/runtime failure; production
  now emits only a fixed message and setup-run ID, and the test proves raw
  secrets and paths do not enter the log payload.
- CodeRabbit inline findings were verified and resolved: migration constraint
  operations use the physical PostgreSQL name in both directions, guide
  continuation recovery publishes the continuation directly with an
  independent bound, and the two documentation claims now match implementation.
- After AUTH PR #248 merged, ART was rebased as the single successor migration
  `0049_guide_source_v2`. Hosted run `30784652926` proved the exact combined
  AUTH+ART public-schema fingerprint; the fail-closed test constant now records
  that observed value.
- Hosted run `30786024204` reduced the suite to one stale synthetic fixture: a
  policy-context test created setup generation 2 while all verified ART lineage
  remained generation 1. The test now reuses the exact source setup generation
  and varies only the effective-policy context it is intended to isolate.
- Hosted run `30786751487` passed the complete project lifecycle and exposed
  four task corruption tests whose shared helper deleted an immutable,
  ART-bound setup run. The helper now clears only its mutable post-submit
  output pointer before removing the generated policy and preserves all
  verified guide-binding lineage.
- Hosted run `30787408677` passed both project and task lifecycle lanes. The
  remaining shared-foundations failures were reconciliation-only: the OpenAPI
  inventory now records the exact merged AUTH surface, the ART-admission
  migration fixture uses the columns that existed at revision `0028`, and
  downgrade tests expect the outer `0049` clean-cut guard that necessarily
  protects populated guide-source lineage before older migration guards can
  run. Direct migration-function tests continue proving the superseded `0039`,
  `0040`, and `0042` populated-evidence guards independently.

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

- The database-backed migration-fixture repairs require the next hosted Backend
  semantic lane run because no local test database URL is configured. The
  focused OpenAPI contract test passes locally.
- CodeRabbit's latest incremental review reported no new actionable findings;
  all earlier inline findings were checked against the final diff.
