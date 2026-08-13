# Authorization Handoff: WS-CON-001

## Current baseline

Current `main` is `b47a7e64f7d75cda8a0681d1aff3bf0c4a5be4aa` with the AUTH
actor, grant, fixed-service, prepared-mutation, project-guide, policy-mutation,
and REV-readiness foundations plus merged REV PLAN4 and ART foundations. The
database is at migration `0052_legacy_intake_removal`. These foundations do
not create CON runtime, activate CON behavior, or give an outbox dispatcher
feature authority.

AUTH owns identifiers, stable permission mappings, principals, grants,
fixed-service identities and matrix rows, prepared authorization, evaluators,
availability, and activation. CON owns canonical contribution and compensation
resource loaders, policy and binding facts, lifecycle guards, hidden behavior,
and feature tests. Neither subsystem imports the other's repositories or
mutates the other's records.

## Required delivery pattern

Every protected CON boundary follows:

```text
AUTH registers the exact planned action and authority contract
-> CON merges canonical hidden behavior using AUTH-owned ports
-> AUTH integrates the exact evaluator and activates the action
-> cross-initiative release proof enables the surface
```

Registration and provisioning do not imply activation. A dispatcher action
does not confer any handler's feature authority. Query paths use request-scoped
authorization plus canonical loaders; mutation paths use the prepared-mutation
protocol and one caller-owned commit.

## AUTH deliveries required by CON

| CON boundary | Required AUTH delivery | Current disposition |
|---|---|---|
| `03A` binding persistence | none; schema stores only canonical actor identity and non-secret route facts | CON may proceed |
| `03B` policy persistence | none; no command or protected route | CON may proceed |
| `02C` lifecycle audit participant | none; caller supplies already-authorized typed facts | CON may proceed |
| `04A` binding commands | `compensation.adapter_binding.{read,create,suspend,resume,retire}` mapped to `compensation.adapter_binding.manage` with exact Finance authority | register before hidden service; activate after it |
| `04B` policy commands | `contribution.policy.{read,create_draft,update_draft,publish,retire}` mapped to `compensation.policy.manage` with exact Finance authority | register before hidden service; activate after it |
| `05A` guide-activation validation/persistence | existing guide activation authority; later TASK readiness/claim authority remains TASK/AUTH-owned | CON supplies no TASK composition; exact guide/task/assignment lineage must be proven before claim activation |
| `06` former review-claim lookup | none | planned retirement; REV inherits admitted task-locked policy and AUTH adds no CON lookup path |
| `07` review decision participant | existing planned `review.decision` contract | REV owns composition/commit; AUTH later activates |
| `02B` dispatcher | `outbox.dispatch`, closed dispatcher identity, singleton matrix row, provisioning, admission, typed context, evaluator, and availability | blocked; schedule after AUTH delivery |
| `08B` fulfillment callback | independently approved reporter identity/action/matrix contract | not inherited from dispatcher |
| `08A` and `10C` executors | an exact feature identity/action/matrix contract for each executor | not inherited from dispatcher |
| `10A/10B` reads and operations | exact self/project/operations actions and evaluators | register from the final route manifest |

The proposed action names are interface inputs for AUTH planning, not runtime
registration by CON. AUTH chooses the exact activation custodian and proves
principal isolation, stable mappings, negative cases, and hidden-to-active
transition. CON does not add AUTH enums, owners, grants, service identities,
matrix rows, or evaluators.

## Principal and transaction invariants

- Human contribution and award reads use actor-self or one exact eligible
  same-project administrative grant; concealment and pre-filtering are owned by
  the product loader.
- Task claim uses the exact active same-project submitter authority.
- Review claim and decision use the exact active same-project reviewer
  authority plus REV-owned no-self-review and lifecycle facts.
- FinalAcceptance creation is an internal consequence of an authorized
  `review.decision=accept`; it has no separate public action.
- Fixed services require a verified token, active canonical actor/link, closed
  ServiceIdentity, exact static row, active action, and canonical resource
  context. Database grants never substitute for that path.
- AUTH and feature participants flush only. The owning route, service command,
  or callback commits once.
- Provider credentials, opaque provider references, balances, and ledger data
  never enter authorization contexts or audit payloads.

## Immediate AUTH ask

No AUTH change blocks planning or CON `03A`, `03B`, or `02C`. Before CON `04A`
or `04B`, AUTH must publish the exact registration contracts above. Before CON
`02B`, AUTH must deliver the complete dispatcher identity/admission/action
contract. That later dispatcher work must not delay the persistence and
transaction-participant foundations now needed by REV.

This handoff authorizes no implementation and starts no chunk.
