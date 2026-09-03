# PR Trust Bundle: WS-ART-001-02C2

## Chunk

`WS-ART-001-02C2` - Verification Publication And Fencing

Reviewed implementation SHA: `59fbab56e6dcb07c32265e4eb7cc0653b595e1ed`

Trusted base: `c559d556225761d4f5ab5842ea09d8b70df9be58`

Merge intent: `.agent-loop/merge-intents/WS-ART-001-02C2.json`

## Goal And Scope

Resolve committed artifact puts, publish bounded pending work, verify complete
provider reads, and fence terminal transitions without activating product
callers, recovery, Operator routes, background writes, or schedules.

## What Changed

- Added caller-only provider writes and observation-only ambiguous-result
  resolution, durable verification jobs, immutable receipts, terminal fences,
  bounded publication, and complete-read deadlines.
- Kept migrations linear through `0030_artifact_verification` after shared
  outbox migration 0029.
- Fixed the hosted outbox privacy failure by detaching sanitized public-error
  tracebacks from service/session/rollback state while preserving caller-owned
  transactions and persistence behavior.
- Integrated the new four-shard Backend CI and exact authenticated coverage
  fan-in from PRs #163/#164 without altering its workflow, thresholds, or gates.
- Integrated AUTH-PREP from PR #162 without adding an ART consumer or activation.
  Production remains deny-only and all ART actions remain planned.

## Deterministic Evidence

```text
Alembic heads: 0030_artifact_verification (single head)
Agent gates: 91 passed
Final state assertion: 1 passed
Shard-compatible changed-test collection: 108 collected
Focused outbox/helper privacy matrix: 84 passed
Fresh isolated migration integration: 3 passed
Focused ART matrix: 342 passed, 1 disclosed non-reproduced observation
Scoped ART coverage: 92.75% (floor 90%)
git diff --check: PASS
```

Historical run 29751926993 passed 1,783 tests at 87.23 percent global coverage
before final reconciliation. It is not current-head proof.

## CI Integrity And Review

All nine exact-SHA internal tracks completed with no blocker. Candidate CI files
are byte-identical to trusted main: four fixed shards, immutable manifests and
bundles, required upstream success, exact fan-in, API E2E, a 78 percent global
floor, and cumulative 90 percent scoped floors remain mandatory.

## External Review

| Source | Status | Notes |
|---|---:|---|
| GitHub Agent Gates | Pending | Must run on the published evidence head. |
| GitHub Backend | Pending | Must prove all four shards, API E2E, exact fan-in, and coverage floors. |
| CodeRabbit | Pending | Current-head review required after publication. |
| Human review | Pending | Only the user may approve PR #159 for merge. |

## Remaining Risks And Human Focus

- Verify AUTH-PREP remains consumer-neutral and ART remains unavailable.
- Verify stale generation, resource drift, or revoked authority writes no
  terminal fact.
- Verify acknowledgement loss cannot cause a second provider write.
- Verify the sharded fan-in rejects incomplete or mismatched artifacts and
  preserves every coverage threshold.
- AUTH activation, 02C3 recovery, 02D Operator/readiness, and product cutover
  remain separately started work.

## Human Merge Ownership

- [ ] GitHub Agent Gates, sharded Backend, and CodeRabbit pass on the final head.
- [ ] I understand the old unsharded pass is historical only.
- [ ] I explicitly approve PR #159 for merge.
