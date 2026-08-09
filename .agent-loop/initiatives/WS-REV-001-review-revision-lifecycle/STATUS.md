# Status: WS-REV-001 Review And Revision Lifecycle

## Current status

`WS-REV-001-03A2` merged through PR #280. Merged CON-03B PR #274 supplies the canonical
`contribution_policy_versions(id, project_id)` foreign-key target. 03A2 owns
only ReviewLease and preference persistence integrity; it adds no claim,
transition, policy-selection, route, or external-owner behavior.

WS-CON-001-PLAN5 is the merged cross-specification input for revision behavior:
a human `needs_revision` atomically keeps/rebases/blocks the complete applicable
next-attempt guide and policy context, including the submitter
ContributionPolicyVersion. Existing Submissions, Reviews, leases,
ContributionRecords, and awards remain immutable; checker remediation remains
distinct.

`WS-REV-001-03A1` implements the hidden queue/admission persistence foundation.
PR #262 is reconciled with trusted main `2feaf47d`; ART retains migration 0050
and REV owns its exact 0051 successor. The chunk adds no REV route, action
activation, checker hook, lease, Review, revision behavior, or contribution
behavior.

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

The next dependency-ordered boundary is `WS-REV-001-03B`, normalized packet
manifest persistence, after the required ART-owned packet-membership contract
is published. Its skeleton must be expanded and reviewed against current
`main` before implementation. Open pull requests determine transient work.
