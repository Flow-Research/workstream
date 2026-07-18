# Internal Review Evidence: WS-QUAL-001-01A

## Chunk

`WS-QUAL-001-01A`: isolated database runner

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: `d1582ec64b9176c5ead62f695c7a23b48e4c72b9`

Reviewed at: 2026-07-12T18:03:00Z

Reviewer run IDs: external-repair engineering=`qual103_eng_review`;
quality-ci=`qual103_qa_ci_review`; security-product-docs=`qual103_sec_ops_docs`;
original implementation=`qual01a_final_engineering,qual01a_final_quality,qual01a_final_security`

## Reviewed Change

- Added a strict local Postgres provisioner with one unique database and one
  least-privilege ephemeral role per invocation.
- Migrated the owned database to the repository head before child execution,
  stripped admin/nonlocal authority, redacted URLs, and recorded credential-free
  run metadata.
- Added ownership-checked partial-create compensation, exact role/database
  session termination, independent database/role reconciliation, bounded
  process-group termination, and signal-safe cleanup.
- Replaced shared test database fallback with explicit two-phase CI: runner
  lifecycle tests use the step-scoped admin DSN; every remaining test runs in
  the provisioned database.
- Preserved main's 78 percent whole-app gate, 90 percent artifact gate, and
  dedicated API drill database after rebasing PRs #101 and #102.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Partial-create, detached-role, absent-DB, and migration-interrupt cleanup repaired. |
| QA/test | PASS | None | Tests assert real lifecycle outcomes; all 541 collected tests are partitioned exactly once. |
| security/auth | PASS AFTER FIXES | None | Admin authority is parent-only; destructive cleanup is ownership checked and exact. |
| product/ops | PASS | None | Test infrastructure only; product lifecycle and actor behavior are unchanged. |
| architecture | PASS | None | Database lifecycle is separated from inactive coverage-policy chunk 01B. |
| CI integrity | PASS | None | Existing coverage gates remain hard; the 210-minute child deadline leaves a bounded 30-minute cleanup/job window. |
| docs | PASS AFTER FIXES | None | Runbook covers credentials, two phases, timeout, cleanup, redaction, and troubleshooting. |
| reuse/dedup | PASS | None | Existing gate helpers and parallel drill guards were not replaced by a second framework. |
| test delta | PASS | None | No skips, xfails, exclusions, deleted assertions, or selection loss. |

## Deterministic Evidence

```text
Final SHA lifecycle suite: 16 passed in 200.74s
API guard suite: 14 passed
Focused final cleanup/migration cases: 4 passed in 25.24s
Provisioned application suite: 525 passed in 11284.43s
Whole-app coverage: 6466/8159 statements, 79.25% (floor 78%)
Artifact coverage: 1274/1399 statements, 91.07% (floor 90%)
Aggregate collection after final tests: 541 = 16 lifecycle + 525 provisioned
Implementation delta: 700/700 lines outside .agent-loop
Ruff: pass
pip check: pass
Catalog after successful runs: no derived database or role
```

The 525-test application run was completed before the final cleanup-only repair.
Later external-review repairs changed only contracts, the runbook, CI timeout
wiring, and reuse of the unchanged derived-name regex. QA/CI/test-delta review
explicitly accepted the application result as applicable. The final SHA passed
all 16 lifecycle tests and all 14 API guard cases.

## Findings Addressed

- Split the original 923-line combined harness/policy change at the database
  lifecycle versus coverage-policy boundary instead of weakening proof.
- Replaced admin credentials in child URLs with a non-privileged ephemeral role.
- Scoped the admin DSN to the CI Test step.
- Compensated partial role/database creation across interruption windows.
- Added bounded TERM-to-KILL escalation for uncooperative child process groups.
- Preserved existing database sessions on collision and unrelated admin sessions
  during cleanup.
- Reconciled an already-absent owned database without leaking the ephemeral role,
  and terminated role sessions connected to other local databases.
- Preserved exit 130 for interruption during migration and child execution.

## Remaining Risks

- The complete suite took 3:08:04 locally; CI gives the child 210 minutes and
  the job 240 minutes. Runtime regression must trigger performance work, not
  skipped or narrowed tests.
- The whole backend is at 79.25 percent, not the required 90 percent. Inactive
  chunks 01B and 02-06 own the ratchet and genuine behavior gaps.
- Host-level termination can prevent any process cleanup; the runbook and strict
  names allow exact recovery of a residual local database/role pair.

## Stop Condition

Publish 01A for external and human review, then stop. Do not start 01B, chunk 02,
or resume AUTH without the required merge/memory/start checkpoints.
