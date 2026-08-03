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

- REV-03A1 queue/admission-idempotency persistence can begin after PLAN4
  approval without waiting for ART or CON runtime work. Later persistence
  children wait for their named schema/port gates.
- ART gates only manifest/admission/packet consumers that need its final typed
  facts; REV does not wait for ART-07A runtime to define packet semantics.
- REV owns 03A2 completely; CON-03B must merely exist first as its mandatory
  policy-version FK target. CON-06 later supplies claim-time policy lookup;
  CON-07 later supplies canonical decision contribution composition.
- ART must publish a contract-only packet-membership port before REV-03B. ART-
  07A then consumes the merged REV lease/manifest; this removes the former
  circular gate.
- AUTH/XINT/CON planning status labels are partly stale. Future REV children
  must verify exact current-main code and signed merges; REV will report those
  owner-doc gaps rather than edit foreign plans.
- Missing external behavior is reported to its owner and never implemented in
  REV.

## Next step

Await human approval. Then refresh and implement only `WS-REV-001-03A1`
queue/admission-idempotency persistence from then-current main. Stop before
03A2.
