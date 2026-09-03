# PR Trust Bundle: WS-ART-001-02C1

## Chunk And Intent

`WS-ART-001-02C1` - Admission And Put-Attempt Foundation

Reviewed implementation SHA: `535069cfb1a7312d731bb14a6023ceb0894402e9`

Trusted base: `8d5eb15b384fd75787ce98a099400a1d335d2560`

Merge intent: `.agent-loop/merge-intents/WS-ART-001-02C1.json`

Create the durable PostgreSQL admission and prepared-attempt transaction that
must commit before provider I/O while keeping execution and product cutover
inactive.

## Design And Scope

- Workstream derives deployment, project, producer, and applicable task scopes.
- Unique provisional/completed charges count once per scope and exact content;
  released charges may be reacquired only under locked capacity checks.
- Actors owns exact profile/link locking and returns frozen primitive proof in
  the caller's admission transaction; ART makes no AUTH permission decision.
- One namespace claim, complete charge set, and `prepared` attempt commit
  atomically. Prepared scheduling/execution fields remain inactive and null.
- No provider write/observation, verification, publication, recovery, Celery
  execution, route, product cutover, task claim, reviewer lease, R2, or Flow
  Node path is included.

## Acceptance Proof

- [x] Callers cannot supply, omit, or weaken admission scopes or limits.
- [x] Exact actor/link and canonical product relationships are locked and
  revalidated without crossing actor persistence ownership.
- [x] Same content is charged once per applicable scope under real concurrent
  ledger contention.
- [x] Concurrent distinct content cannot oversubscribe a shared scope.
- [x] Reservation failure leaves no partial charge, attempt, receipt, audit
  success, or provider call.
- [x] A committed prepared attempt is required before any later provider work.
- [x] Prepared `next_run_at`, executor, lease, terminal, replica, and receipt
  fields are null and execution generation is zero.
- [x] Exactly one schema-v2 merge intent names only inactive successor `02C2`
  and requires a separate explicit start.

## Tests And Checks

```text
371 focused tests PASS in 757.38s
Scoped changed-subsystem coverage 94.02% (required 90%)
Alembic head 0028_artifact_admission
Ruff PASS
Configured docstring coverage PASS at 90.5%
Stale artifact contract scan PASS
88 agent-gate tests PASS
Markdown links PASS
Schema-v2 merge-intent validation PASS
git diff --check PASS
```

GitHub Backend remains authoritative for the full isolated repository suite and
78-percent repository coverage floor.

## Internal Review

All nine required tracks reviewed exact SHA `535069cf...`: senior engineering,
architecture, QA/test, security/auth, product/ops, reuse/dedup, CI integrity,
test delta, and docs. QA's initial High concurrency-proof finding was repaired
and passed on rerun. Docs' stale-evidence finding was repaired by regenerating
the exact-SHA evidence, this bundle, external status, and initiative state. No
blocking finding remains and every reviewer session is closed.

## External Review

| Source | Status | Notes |
|---|---:|---|
| GitHub Agent Gates | Pending | Must run on the published rebased final head. |
| GitHub Backend | Pending | Must prove the full suite, scoped gates, and 78-percent floor. |
| CodeRabbit | Pending | A fresh current-head review must be requested after publication. |
| Human review | Pending | Only the user may approve PR #154 for merge. |

## Remaining Risks

- Admission is intentionally not connected to provider execution or product
  submission routes.
- Native AWS remains unavailable until its separately owned live proof.
- External checks have not yet run on the final rebased head.

## Human Review Focus

- Can a producer omit a scope, weaken capacity, or substitute identity/context?
- Does every success commit the complete ledger and exactly one prepared
  attempt before provider side effects?
- Do rollback, replay, release/reacquisition, and concurrent contention preserve
  exact accounting?
- Are provider execution, verification, recovery, and product routes absent?

## Human Merge Ownership

- [ ] I can explain what changed and why.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] GitHub CI and external review pass on the final head.
- [ ] The user explicitly approved PR #154 for merge.
