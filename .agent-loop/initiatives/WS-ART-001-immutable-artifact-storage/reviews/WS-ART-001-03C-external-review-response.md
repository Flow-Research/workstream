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
- CodeRabbit's latest incremental fixture-architecture comment was valid: the
  complete verified-guide lineage helper now lives in a shared test utility,
  and project and task tests consume that single implementation without
  importing one product test module from another.
- The remaining valid review cleanups are also applied: stale contracts reject
  all three removed v1 identity fields; verified agent-input projection is
  shared; extraction slot naming and reader typing are explicit; the dispatch
  predicate is typed and documented; the migration records its empty-table
  downgrade dependency; the eligibility probe avoids a pointless row lock;
  repository layout is conventional; and the unused source-label threat
  categories were removed from the parametrized test.
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
- Distributed Backend run `30790674519` passed project lifecycle, task
  lifecycle, shared foundations, and schema contracts B. Schema contracts A
  exposed one migration-scope test that seeded pre-0045 rows and then upgraded
  through the intentional `0049` clean-cut refusal. The historical-preservation
  test now stops at revision `0045`, which is the migration it proves; separate
  tests continue proving the current-head `0049` refusal.
- Distributed Backend run `30800292363` passed all five semantic lanes and
  exposed one real-API helper authority mismatch in the final fan-in job. The
  helper created the guide-source snapshot with the token carrying the local
  Project Manager grant, but attempted the hidden artifact upload with a token
  carrying only a legacy Flow role claim. The API correctly returned the
  resource-hiding 404. The upload now uses the same locally authorized token as
  snapshot creation; no production authorization behavior changed.
- CodeRabbit's review of repair head `feb40f9a` found no code defect and one
  trivial compound-modifier wording issue in the trust bundle; the wording is
  now hyphenated without changing evidence meaning.

## Comments deferred

- Holding guide/read row locks through the authorized provider read remains
  intentional for this L1 boundary: splitting the transaction would violate
  the reviewed transaction-bound AUTH/read contract.
- Moving verified-report queries from `ProjectService` into the repository is
  a non-functional ownership refactor outside this clean-cut chunk.
- A dedicated continuation-scan interval is explicitly optional for v0.1; the
  shared bounded scan interval remains the approved operational surface.
- The pre-submit worker wrapper retains the stable Celery/test seam and is not
  an independent execution path.

## Human decisions needed

- None. Human merge approval remains required after hosted checks pass.

## Commands rerun

- Ruff over backend application, tests, backend scripts, and repository scripts.
- Python compilation for backend application and tests.
- Stale authorization and artifact documentation checks.
- Lightweight agent gates and Markdown link validation.

## Required next evidence

- Hosted Backend and Agent Gates rerun on the exact E2E repair head.

## Remaining risks

- All five distributed semantic lanes passed on run `30800292363`; the final
  real-API fan-in proof remains pending on the repaired helper.
- CodeRabbit's latest incremental review reported no new actionable findings;
  all earlier inline findings were checked against the final diff.
