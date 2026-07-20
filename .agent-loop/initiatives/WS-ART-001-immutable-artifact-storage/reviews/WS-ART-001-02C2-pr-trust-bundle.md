# PR Trust Bundle: WS-ART-001-02C2

## Chunk

`WS-ART-001-02C2` - Verification Publication And Fencing

Reviewed implementation SHA: `ad46958ac11e8b1acff98c0c5f79c9a2a68797b9`

Trusted base: `fe0e4492a7de8699c06a52921cbdaa8a1a22e567`

Merge intent: `.agent-loop/merge-intents/WS-ART-001-02C2.json`

## Goal And Scope

Resolve committed artifact puts, publish bounded pending work, verify complete
provider reads, and fence terminal transitions without activating product
callers, recovery, Operator routes, background writes, or schedules.

## What Changed

- Added caller-only provider writes and read-only ambiguous-result observation.
- Added durable verification jobs and operation, observation, and verification
  receipts with executor/generation fences and total read deadlines.
- Added bounded post-commit publication scanning; production remains deny-only
  with no Beat entry.
- Kept migrations linear through `0030_artifact_verification` after shared
  outbox migration 0029.
- Fixed hosted outbox privacy failures by severing sanitized error tracebacks
  from service/session/rollback state and bounding test inspection to causal ORM
  state. No commit, rollback, close, envelope, success, or persistence behavior
  changed.
- Integrated PR #158 ART custody and PR #160 REV custody. Both only transfer
  owner metadata; all 25 ART and 19 REV actions remain planned.

## Acceptance Evidence

```text
Alembic heads: 0030_artifact_verification (single head)
Fresh isolated migration integration: 3 passed
Focused outbox/helper privacy matrix: 84 passed
Agent gates: 88 passed
Focused ART matrix: 342 passed, 1 disclosed non-reproduced observation
Scoped ART coverage: 92.75% (floor 90%)
Verification + architecture smoke: 15 passed
Ruff: PASS
Stale wording/contracts: PASS
Markdown links: PASS
git diff --check: PASS
```

The local full suite was stopped at the user's request because the machine was
under heavy contention. It is not pass evidence. Hosted Backend must prove the
exact published head, full suite, 78 percent global floor, and scoped floors.

## CI Integrity And Review

No workflow, threshold, ignore, skip, xfail, retry, or failure bypass was added.
All nine exact-SHA internal tracks completed. No implementation blocker remains;
CI, QA, product/ops, and senior review explicitly retain hosted Backend as a
required external condition.

## External Review

| Source | Status | Notes |
|---|---:|---|
| GitHub Agent Gates | Pending rerun | Earlier published head passed; exact evidence head must rerun. |
| GitHub Backend | Pending rerun | Run 29739194203 failed two outbox privacy assertions; bounded repair is ready for hosted proof. |
| CodeRabbit | Pending current-head review | Earlier head passed with no comments; no result is carried forward. |
| Human review | Pending | Only the user may approve this PR for merge. |

## Remaining Risks And Human Focus

- Confirm hosted Backend closes both original outbox privacy failures without a
  new artifact regression or coverage drop.
- Confirm stale generations, changed resource facts, or revoked identities
  cannot persist terminal state.
- Confirm acknowledgement loss cannot cause a second provider write.
- Confirm production tasks remain deny-only, unscheduled, and unreachable.
- AUTH activation, 02C3 recovery, 02D Operator/readiness, and product cutover
  remain separately started work.

## Human Merge Ownership

- [ ] GitHub CI and current-head external review pass.
- [ ] I understand the disclosed local interrupted-run limitation.
- [ ] I explicitly approve PR #159 for merge.
