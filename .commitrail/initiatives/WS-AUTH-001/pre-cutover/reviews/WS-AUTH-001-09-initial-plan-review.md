# WS-AUTH-001-09 Initial Preimplementation Plan Review

## Verdict

`FAIL - SPLIT REQUIRED`

No runtime application or migration code was written under the rejected
contract.

## Required tracks

| Track | Result | Blocking findings |
|---|---|---|
| senior engineering / architecture / CI / docs / reuse | FAIL | Combined multiple L1 boundaries; omitted migration/model/test ownership; did not define exact actions/resources; collided with future migration `0023`; made startup circular. |
| QA / product / test delta | FAIL | Canonical route conflict; incomplete state/replay/privacy/timestamp/503 contracts; service provisioning and persisted-startup readiness were circular; scope was not reviewable as one PR. |
| security / auth | FAIL | Final-admin lock order was underspecified; service identity and assignment authority were ambiguous; human admin dependencies risked being broadened to service callers; planned artifact actions could not yet authorize. |

## Accepted repair

The user accepted a smaller ServiceAccount-style model:

- a service ActorProfile is the stable fixed local principal;
- `ActorProfile.service_identity` is immutable, unique, closed, required for a
  service, and null for a human;
- ActorIdentityLink alone binds the canonical issuer and opaque subject;
- one frozen typed seven-identity/eleven-ActionId matrix supplies service
  candidates;
- no service registration or action-assignment table exists;
- every artifact action remains planned while WS-ART supplies the hidden
  resource facts, guards, behavior, and typed manifest required for a later
  AUTH-owned evaluator integration and activation.

Parent AUTH-09 is split into 09A identity/catalogue foundation, 09B controlled
service provisioning, 09C bounded actor/link reads, and 09D lifecycle mutations
with final-admin concurrency. XINT subsequently made 09E fixed-service runtime
admission mandatory before the availability-neutral ART/REV custody transfers
and prepared-mutation protocol. Repaired 09A requires fresh exact-head L1
review before implementation.
