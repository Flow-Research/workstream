# Status: WS-REV-001 Review And Revision Lifecycle

## Current status

PLAN4 end-to-end planning refresh is complete and internally reviewed from
current main `3479ee71`. No REV runtime module, table, route, action activation,
or product behavior exists.

AUTH `WS-XINT-003-02A` through `02D` are merged. REV now has stable policy
lineage/mutation, complete unavailable action/principal registration, and typed
authorization contract models for every approved lifecycle action.

## Boundary

REV starts from an existing immutable Submission plus a durable final current
CheckerRun `allow_review` and exact verified ART binding facts. It owns queue,
lease, packet semantics, Review history, revision replay, FinalAcceptance,
recovery, projection, release control, and lifecycle orchestration.

REV does not own Project/Task/Submission/Checker/AUTH/ART/CON internals.

## Parallel safety

- Core REV persistence can begin after PLAN4 approval without waiting for all
  ART or CON runtime work.
- ART gates only admission/packet consumers that need its final typed facts.
- CON gates only lease policy freeze and canonical decision composition.
- Missing external behavior is reported to its owner and never implemented in
  REV.

## Next step

Await human approval. Then refresh and implement only `WS-REV-001-03A1`
queue/admission-idempotency persistence from then-current main. Stop before
03A2.
