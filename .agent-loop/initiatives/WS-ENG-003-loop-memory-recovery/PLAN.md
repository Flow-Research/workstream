# PLAN: WS-ENG-003

1. Add a closed recovery certificate naming PR #166 by exact initiative, chunk, PR number, and merge SHA, plus activation chunk `WS-ENG-003-01`.
2. Before sequential reconciliation, collect the exact resolved protected-main target record and require the planned merge list to end at that same SHA. Activate only when that target record is `WS-ENG-003-01`; derive its exact PR number from the normal unique GitHub merge-record collector.
3. Require the recovery plan to be exactly PR #166 followed by the recovery target, reject inventory collisions with signed state, and write the two exact entries only to bounded ephemeral runner state.
4. Pass the out-of-band inventory to both reducer calls. Each reducer selects and consumes only its own unique exact entry without writing any recovery entry into canonical state or ledger history.
5. Before signing, require canonical source to equal the resolved target and require both recovery identities to be absent while unrelated legacy exemptions remain unchanged.
6. An unpublished failed run may reconstruct the same inventory from the same immutable target. A successful empty-plan replay recognizes the already-current target and does not re-inject anything.
7. Add fail-closed tests for wrong/later/non-final targets, wrong identity/SHA, ambiguous target evidence, collision, order, partial consumption, retry, replay, and future enforcement.
8. After merge, verify Loop Memory replays successfully through both records.
