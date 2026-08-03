# Status: WS-CON-001 Contribution And Compensation

## Current baseline

- Reconciled main: `10720382cd9639f00f09578f772b97ab3afc358b`.
- Backend CI for that SHA: passed.
- Alembic head on main: `0049_rev_auth_readiness`.
- CON-01 and CON-02A are merged.
- No CON runtime chunk is active in this worktree.
- Runtime contains shared outbox persistence only; contribution, compensation,
  dispatcher, fulfillment, operations, and CON API behavior remain absent.
- The pre-existing local deletion of the archival reference PDF is user-owned
  and excluded from this planning change.

## Current external work inspected

### AUTH/XINT

Merged through PR #257:

- review/revision policy identity and mutations;
- complete planned REV action/principal catalogue;
- typed fail-closed REV resource, PREP, and read contracts.

This is readiness for hidden REV implementation, not a live review lifecycle.
CON dispatcher and protected CON surface identifiers remain unregistered.

### ART

Guide byte ingest, binding, extraction, and sufficiency foundations are merged.
AUTH guide binding/read activation is merged. ART PR #249 is the verified
guide-source cutover; it remains open and unmerged. Its proposed 0050 migration
is not part of main. Re-check its checks and merge state before implementation.

### REV

REV PR #258 is merged planning-only end-to-end evidence. It correctly
preserves CON ownership and identifies CON-03B as
the policy FK prerequisite for REV-03A2.

## Corrected CON priority

The old plan incorrectly made dispatcher work the predecessor of all CON
schema work. Current dependency analysis yields:

1. PLAN4 planning reconciliation.
2. CON-03A adapter-binding persistence.
3. CON-03B contribution-policy persistence, unblocking REV-03A2.
4. CON-02C lifecycle-audit participant before REV-04B.
5. Hidden policy/binding behavior and legacy clean cut as AUTH contracts become
   available.
6. Contribution/award persistence after REV provides stable FK targets.
7. Atomic REV/CON participant after both sides' lineage exists.
8. Dispatcher and fulfillment later, after exact AUTH service registration.

## Current blockers

- CON-02B: missing `outbox.dispatch`, `workstream.outbox.dispatcher`, exact
  matrix/context/PREP support, and AUTH activation plan.
- CON-04A/04B and later protected surfaces: exact AUTH manifests are not yet
  registered.
- CON-05A/05B: deterministic legacy-row classification remains a human data
  decision.
- CON-03C: REV Review/ReviewLease/FinalAcceptance tables are not implemented.
- CON-06/07: corresponding REV lease/decision caller contracts are future.
- Migration allocation: refresh after PR #249 and any other migration-bearing
  merge; do not assume 0050/0051.

## Immediate next action

Publish the reviewed PLAN4 planning repair without the user-owned PDF deletion.
After PLAN4 merges and the human approves implementation, refresh main and
implement only CON-03A. Stop at its PR checkpoint; do not start 03B or another
CON chunk automatically.
