# Authorization Handoff: WS-CON-001

## Current baseline

Current `main` contains the AUTH actor, grant, fixed-service,
prepared-mutation, project-guide, policy-mutation, and REV-readiness
foundations plus merged REV PLAN4, ART foundations, and CP02 hidden CON
adapter-binding behavior. The old `0052_legacy_intake_removal` identifier is
historical merge evidence. Current `main` ends at
`0006_contribution_policy_operations`, whose tracked predecessor is
`0005_compensation_adapter_identity`. Older `0050`, `0053`, and `0055`
identifiers are historical pre-baseline merge evidence, not active graph heads.
CP03A installs the target identity and owner eligibility without action-bearing
service membership; CP03B activates only the four exact Finance Authority
boundaries. CP04A implements hidden policy draft behavior behind deny-default
authorization. No public CON route, ContributionPolicy authority, or
outbox-dispatcher authority is active.

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
| `CP01A` binding registration | exact binding actions, typed contexts, custody and permission mapping; retirement/callback/fulfillment excluded | register unavailable first |
| `CP01B` policy registration | exact `contribution.policy.*` actions, typed contexts, custody and permission mapping | register unavailable after CP01A and before hidden services |
| `CP03A/CP03B` binding prerequisite/activation | exact adapter target identity and owner eligibility, then exact CP02-proven binding actions only | keep unavailable through CP03A; activate in CP03B |
| `CP05` policy activation | exact CP04A/CP04B-proven policy actions only | activate after both hidden proofs |
| `CP06-CP08` validation and owner persistence | existing guide activation authority; later TASK readiness/claim authority remains TASK/AUTH-owned | CON validates only; PROJECT/TASK own writes |
| `06` former review-claim lookup | none | planned retirement; REV copies the admitted Submission's immutable attempt version, verifies Task/Assignment only for equality, and performs no CON/current-policy lookup |
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

No AUTH change blocks planning or completed CON `03A`, `03B`, or `02C`. CP01A
and CP01B separately register binding and policy authority while unavailable.
CP01C corrects binding identity and lifecycle-generation facts before CP02.
CP02 is merged with hidden CON behavior. CP03A installs the exact target identity
and owner eligibility without activation; CP03B is complete and
activates only the four exact CP02 Finance Authority boundaries. CP05 later
activates only CP04A/CP04B's merged hidden proof. CP04A is complete; CP04B is
the remaining hidden behavior prerequisite. Before CON
`02B`, AUTH must deliver the complete dispatcher identity/admission/action
contract. That later dispatcher work must not delay the persistence and
transaction-participant foundations now needed by REV.

This handoff authorizes no implementation and starts no chunk.
