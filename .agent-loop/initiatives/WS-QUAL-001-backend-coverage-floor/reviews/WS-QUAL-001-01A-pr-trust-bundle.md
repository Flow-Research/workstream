# PR Trust Bundle: WS-QUAL-001-01A

## Chunk

`WS-QUAL-001-01A`: isolated database runner

## Goal And Intent

Give every backend test run a unique migrated local Postgres database without
sharing state or exposing database-admin authority to the test child. Behavior
and safety proof outrank coverage percentage gains.

## What Changed And Why

- Added `run_isolated_tests.py` to create a strict database and ephemeral role,
  migrate, execute, redact, and clean up.
- Made `WORKSTREAM_TEST_DATABASE_URL` mandatory for DB-backed tests.
- Allowed strict derived local names in both destructive API drill guards.
- Added real Postgres lifecycle tests for least privilege, collisions,
  concurrency, partial creation, migration, signals, timeout, detached sessions,
  cleanup failure, and URL redaction.
- Changed Backend CI to a complete two-phase partition and retained main's 78
  percent whole-app and 90 percent artifact gates.
- Added the backend testing runbook, a 210-minute child deadline, and a
  240-minute job timeout based on measured complete-suite runtime.

## Design And Alternatives

The parent uses an admin DSN only to provision and destroy resources. The child
receives a random role with no superuser, create-role, create-database,
replication, inheritance, or bypass-RLS authority. Destructive operations use
validated identifiers and parameterized catalog values.

Rejected: a shared database, admin child credentials, test skips, coverage
exclusions, a single 1,100-line PR, or hiding the three-hour runtime.

## Scope And Product Behavior

No `backend/app/**`, migration, public API/schema, auth product behavior, or
coverage-policy implementation is changed. Chunk 01B remains inactive.

## Acceptance Proof

- Final reviewed SHA `d1582ec64b9176c5ead62f695c7a23b48e4c72b9`.
- 16 lifecycle tests and 14 API guard tests passed on final SHA.
- 525 provisioned application tests passed; whole-app coverage is 79.25 percent.
- Artifact subsystem coverage is 91.07 percent.
- All 541 tests are executed exactly once across the two CI phases.
- Ruff, dependency, stale-wording, Markdown-link, diff, and catalog-clean checks
  passed during the reviewed loop.
- Implementation is exactly 700/700 lines; `.agent-loop` evidence is excluded.

## Test Delta And CI Integrity

No test was deleted, skipped, xfailed, weakened, or added solely to hit a line.
The single `--ignore` in phase two is exactly offset by executing that full test
file in phase one. Existing coverage commands remain mandatory. The timeout was
raised because the complete measured run exceeded three hours; selection and
thresholds were not changed.

## Reviewer Results

All required tracks pass after repairs: senior engineering, QA/test,
security/auth, product/ops, architecture, CI integrity, docs, reuse/dedup, and
test delta. No sub-agent session remains open.

## External Review

CodeRabbit posted seven requests. All valid contract, runbook, timeout, and
reuse findings were repaired; role-aware cleanup was retained with explicit
ownership justification and real-catalog proof. The initial Agent Gates wording
failure was repaired. Final GitHub checks and human review remain pending.

## Remaining Risks And Follow-Up

- CI runtime is high and must be monitored.
- Whole-backend coverage remains 79.25 percent. 01B and 02-06 remain required
  unless later complete-suite evidence legitimately collapses milestones.
- Host shutdown may leave a strictly named local resource requiring exact
  operator cleanup.

## Human Review Focus

- Parent-only admin authority and child least privilege.
- Ownership checks and cleanup after partial creation, signals, and child-owned
  database removal.
- Exact 16 + 525 test partition with both inherited coverage gates preserved.
- The database-runner versus coverage-policy chunk split.

## Human Merge Ownership

- [ ] I can explain the provisioning and cleanup authority boundary.
- [ ] I verified CI and external review results.
- [ ] I confirm 01B and AUTH have not started.
- [ ] The user explicitly approved this specific PR for merge.
