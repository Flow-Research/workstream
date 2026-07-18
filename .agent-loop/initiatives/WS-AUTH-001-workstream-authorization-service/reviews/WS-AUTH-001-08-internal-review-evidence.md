# WS-AUTH-001-08 Internal Review Evidence

Reviewed code SHA: `a284a718e68f08e072cb965cc5834bcc7ab45ee9`
Reviewed implementation SHA: `34f87a5aa7d75897349f64f5e904cb1847af019b`
Reviewed at: `2026-07-16T07:43:50Z`
Reviewer run IDs: auth08_final_senior, auth08_final_qa,
auth08_final_security
Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

## Deterministic Evidence

- The final authorization, audit, auth, actor, API-control, and rate-control
  suite passed 275 behavior tests against fresh isolated PostgreSQL at migration
  head `0022_bootstrap_admin_grants`.
- Branch-aware focused coverage is 90.17 percent, above the required 90 percent
  threshold. The administrative mutation service reports 100 percent coverage.
- Signed-token API behavior proves one-time bootstrap, exact role and scope
  grants, issue/revoke idempotency replay and mismatch, last-administrator
  protection, concealment, and immutable audit/invalidation linkage.
- Decision consumers require the exact frozen action, permission, authority,
  grant, scope, resource digest, revalidation state, and reason digest before
  any mutation or denial evidence is written.
- Independent substitution tests prove an issue decision cannot be reused for
  another role and normal revoke decisions cannot be exchanged with
  existing-idempotency mismatch decisions; every rejected case crosses no write
  boundary.
- The inherited AUTH-07B transaction defects are repaired: dependency teardown
  rolls back rather than committing feature work, evidence SQL failures map to
  retryable 503 responses, and successful existing-actor self routes restore
  canonical verification timestamps under route-owned commits.
- Ruff, stale Workstream wording, stale authorization documentation, changed
  Markdown links, loop-memory validation, 71 agent-gate tests, and diff
  integrity passed.
- After GitHub Backend run `29478021300` exposed a stale retained-revision
  assertion, the full isolated Alembic suite passed all 17 tests. The repaired
  test captures the actual pre-command head and proves every guarded downgrade
  failure leaves that revision unchanged; the dedicated AUTH-08 test retains
  the exact literal `0022_bootstrap_admin_grants` assertion.
- No workflow, dependency, package, test skip, coverage exclusion, or threshold
  changed. GitHub Backend remains authoritative for the repository-wide 78
  percent floor.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | Exact decision-resource isolation is independently proved across every mutation and denial consumer. |
| QA/test | PASS AFTER FIXES | none | Signed API behavior covers replay, mismatch, concealment, distinct revoke targets, and unchanged state on failure. |
| security/auth | PASS AFTER FIXES | none | Typed resource and reason digests prevent role, scope, disposition, and request substitution before writes. |
| product/ops | PASS | none | Access administration and scoped administrative roles are explicit; token claims remain non-authoritative. |
| architecture | PASS AFTER FIXES | none | Central grant-backed authorization remains request scoped and feature transactions retain commit ownership. |
| CI integrity | PASS | none | CI, dependencies, thresholds, skips, and exclusions are unchanged. |
| docs | PASS | none | Bootstrap, role matrices, grant lifecycle, and operational recovery match runtime behavior. |
| reuse/dedup | PASS | none | Administrative decisions reuse the central kernel, repositories, audit writer, and idempotency foundation. |
| test delta | PASS | none | New tests assert behavior and zero-write boundaries rather than only increasing line coverage. |

## Findings Resolved

Review repairs removed caller-controlled evidence request identifiers, bound
every administrative result to its exact frozen authorization decision, and
made revoke replay versus mismatch an explicit typed resource disposition.
Issue and revoke operations now bind complete resource context and raw reason
to their digests before any repository, state, audit, or idempotency write.

The final QA repair distinguishes the acting administrator from the revoked
grant target and proves same-key changed-reason revoke returns the stable 409
mismatch without changing grant or idempotency state. The final senior repair
isolates `resource_context_digest` as the only failing predicate and proves
zero writes for role and revoke-disposition substitution.

GitHub Backend run `29478021300` then found that the historical canonical-actor
downgrade test still expected the former `0021` head after a transactional
guard failure. Repair `cd46420` captures the actual head before the downgrade
attempt and asserts it remains unchanged, preventing both the cleanup cascade
seen in CI and future coupling to a particular later migration. Exact-head
senior/CI, QA/test-delta, and security/architecture re-review passed.

CodeRabbit then identified four valid final-head findings. Repair `a284a71`
adds deferred commit-time bootstrap grant/control invariants on both tables,
uses one exact AUTH-08 evidence-event set for upgrade adoption and downgrade
custody, gives mutation tests a distinct authorizing grant, and synchronizes the
runbook to 57 actions with nine active and 48 planned. The two direct regression
tests and all 17 isolated Alembic tests pass. Exact-head senior/CI/docs/reuse,
QA/test-delta/product, and security/architecture re-review report no remaining
finding.

Valid findings addressed: yes

Open sub-agent sessions: none

## Remaining Gate

Ready PR publication, GitHub Backend, Agent Gates, CodeRabbit, and explicit
human merge approval remain pending. Do not start `WS-AUTH-001-09`
automatically.
