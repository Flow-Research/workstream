# Authorization Handoff: WS-CON-001

## Current baseline

Trusted `main` is `8d5eb15b` after contributor-foundation PR #153, AUTH-09D-B PR #152, ART-02B1 PR #151,
planning-only REV PLAN2 PR #150, AUTH-09D-A PR #148, REV-02 PR #147 and
REV-01 PR #145, layered on AUTH-09C PR #146, ART PR #141, AUTH-09B PR #143,
merged REV planning PR #128, AUTH-09A/AUTH PR #140, and the earlier WS-XINT PR
#139 boundary. The runtime catalogue contains 74 PermissionIds and 65 ActionIds:
17 active and 48 planned. AUTH-09B activates only `actor.service.provision`;
AUTH-09C activates only `actor.profile.read` and `actor.identity_link.read`;
AUTH-09D-A activates only the three actor-profile lifecycle actions;
AUTH-09D-B activates only identity-link revoke/reactivate. PR #153 changes
TaskAssignment/Submission attribution and canonical-human writer validation
only; it adds no action, permission, grant, evaluator, availability,
fixed-service admission, or review runtime. No
WS-CON-specific or task-claim ActionId below is registered. PR #140 still defines the
prepared/custody plan; it does not implement AUTH-PREP, transfer ART/REV custody,
register a CON action, or activate a CON feature action.

AUTH owns identifiers, stable mappings, activation custody, typed resource and
principal contexts, grants, fixed ServiceIdentity/static matrix, AUTH-09E
admission, prepared mutation handles, evaluator dispatch, decision evidence,
availability, and parity. CON owns canonical product loaders, typed resource
facts, lifecycle guards, hidden behavior, and feature tests. Neither side
imports the other's repositories or mutates the other's state.

## Required delivery sequence

Every protected CON surface follows:

```text
AUTH registration checkpoint
  planned ActionId + stable PermissionId + AUTH ActionOwner
  principal class + typed context + prepared protocol when mutating
-> CON hidden-behavior checkpoint
  canonical resource loader + guards + behavior, real kernel still denies
-> AUTH activation checkpoint
  exact evaluator + matched authority + negative proof + active availability
-> joint release checkpoint
```

Registration, provisioning, matrix membership, feature behavior, and activation
are distinct. A provisioned service cannot execute a planned action. CON cannot
turn a fake/test decision into a production allow path.

## Principal models

### Human

- task.claim: exact active same-project `submitter` ProjectRoleGrant;
- review.claim and review.decision: exact active same-project `reviewer`
  ProjectRoleGrant plus no-self-review and lifecycle guards;
- contribution self/award self: exact actor-self relationship;
- administrative policy, binding, project reads, and operations: one exact
  eligible AdminRoleGrant selected by the action evaluator.

The shipping path consumes exact `submitter` and `reviewer` grants. There is no
combined grant and no unrelated project/admin grant substitutes. WS-CON adds no
adjudication grant or action and has no adjudication readiness dependency; any
separate global project-role catalogue state remains AUTH-owned and outside
this transaction.

FinalAcceptance creation has no ActionId. It is an internal REV-owned
consequence of an already-authorized `review.decision` with `accept`; CON only
validates and consumes the locked fact when creating `accepted_submission`.

### Fixed service

The only service admission path is:

```text
verified service token
-> active ActorIdentityLink
-> active service ActorProfile
-> immutable closed ServiceIdentity
-> exact static service-action matrix membership
-> AUTH-09E typed service AuthorizationContext
-> CON-composed canonical ResourceContext
-> decision
```

There is no database service grant or action-assignment row. AUTH locks the
profile/link and validates unchanged ServiceIdentity, static membership, and
active action. Human grants cannot satisfy service actions and services cannot
use human grant candidates. Missing provisioned rows deny the request and block
release readiness, but do not fail application startup or provisioning.

AUTH-09B now exposes `POST /api/v1/service-actors` to an effective system Access
Administrator. It binds the configured issuer and opaque subject to one
already-approved closed ServiceIdentity and creates only the service
ActorProfile/ActorIdentityLink plus bounded authorization, audit, invalidation,
and idempotency evidence. It creates no role, grant, assignment, service-token
admission, or executable service authority. The current seven identities and
eleven static rows are ART-only. Each proposed CON fixed service requires a
separate reviewed identity/action/static-row contract before provisioning and
still waits for AUTH-09E admission and exact action activation.

## Prepared mutation protocol

For `T` actions AUTH locks canonical current human actor/link/exact-grant or
fixed-service actor/link authority first and returns one opaque,
non-serializable `PreparedAuthorizationHandle`. The handle is bound exactly to
the caller session, ActionId, actor-reference kind, actor reference,
idempotency key, and canonical request digest. ServiceIdentity, static matrix
membership, and availability are code-owned validations after profile/link
locks, never database lock targets. CON or the owning feature then locks
product rows in the canonical order and recomposes final typed facts; AUTH
consumes the handle, evaluates once, and stages decision evidence. AUTH and all
feature participants flush only; the route/executor/callback command commits
once. Reused, serialized, caller-constructed, cross-session/action/actor/
request, binding-mismatched, or authority-lost handles deny before product
mutation. A failed substitution attempt does not consume an otherwise valid
handle.

`Q` reads use request-scoped require plus canonical CON loaders, pre-filtered
pagination, and concealment. No authorization result or grant cache survives a
request.

## Proposed core action mappings

These 22 feature-surface mappings preserve existing stable PermissionIds except
for the two explicitly proposed service-only PermissionIds. They are product
proposals, not registered runtime, and they are not a final action count until
the protected execution boundaries are approved. Policy ActionIds use the
canonical `contribution.policy.*` namespace while retaining stable
`compensation.policy.manage` PermissionId compatibility.

| Proposed ActionId | PermissionId | Principal / target | Protocol | Feature owner |
|---|---|---|---:|---|
| `outbox.dispatch` | proposed `outbox.dispatch` | fixed outbox dispatcher / claimed event | T | shared outbox 02B |
| `compensation.adapter_binding.read` | `compensation.adapter_binding.manage` | Finance / ProjectCompensationAdapterBinding | Q | CON-04A |
| `compensation.adapter_binding.create` | `compensation.adapter_binding.manage` | Finance / project binding collection | T | CON-04A |
| `compensation.adapter_binding.suspend` | `compensation.adapter_binding.manage` | Finance / active binding | T | CON-04A |
| `compensation.adapter_binding.resume` | `compensation.adapter_binding.manage` | Finance / suspended binding | T | CON-04A |
| `compensation.adapter_binding.retire` | `compensation.adapter_binding.manage` | Finance / dependency-free binding | T | CON-10B |
| `contribution.policy.read` | `compensation.policy.manage` | Finance / ContributionPolicyVersion | Q | CON-04B |
| `contribution.policy.create_draft` | `compensation.policy.manage` | Finance / project policy collection | T | CON-04B |
| `contribution.policy.update_draft` | `compensation.policy.manage` | Finance / draft version | T | CON-04B |
| `contribution.policy.publish` | `compensation.policy.manage` | Finance / complete draft version | T | CON-04B |
| `contribution.policy.retire` | `compensation.policy.manage` | Finance / published version | T | CON-04B |
| `compensation.fulfillment.report` | proposed `compensation.fulfillment.report` | exact bound service / award and binding | T | CON-08B |
| `contribution.read_self` | `contribution.read_self` | contributor / own record | Q | CON-10A |
| `contribution.read_project` | `contribution.read_project` | exact eligible AdminRole / project collection | Q | CON-10A |
| `compensation.award.read_self` | `contribution.read_self` | beneficiary / own award | Q | CON-10A |
| `compensation.award.read_project` | `compensation.award.read` | D11 role set / project award collection | Q | CON-10A |
| `compensation.delivery.reconcile` | `compensation.delivery.reconcile` | D11 role set / delivery request | T | CON-10B |
| `compensation.status.read` | `operations.status.read` | Operator / bounded status | Q | CON-10B |
| `compensation.reconcile.run` | `operations.reconcile.run` | reason-bound Operator / durable request | T | CON-10B |
| `contribution.projection.rebuild` | `operations.projection.rebuild` | reason-bound Operator / durable request | T | CON-10B |
| `audit.read` | `audit.read` | D11 role set / bounded WS-CON audit | Q | CON-10B |
| `audit.export` | `audit.export` | D11 role set / bounded export | T | CON-10B |

PR #140 approves no `AUTH_CON_*` owner identifiers. After a complete
feature-owned manifest exists, AUTH must assign each registered action to one
exact future `WS-AUTH-001-*` activation chunk and prove unchanged mapping plus
planned availability. CON must not predict or add ActionOwner enum values.

## Core resource guards

- Policy publish locks one active ContributionPolicy selector, draft version,
  both exact ContributionRules, award definitions, and referenced active same-
  project/instrument bindings. Published content is immutable.
- Binding create validates canonical service actor, approved adapter capability,
  project/instrument, and non-secret route identity. Suspend blocks new freezes
  and deliveries but preserves valid callbacks for already-issued awards.
- Binding retire denies any active policy reference, unfinished frozen
  assignment/lease, or unfulfilled award. After retirement only exact replay of
  a previously accepted receipt may be acknowledged.
- Contribution self/project and award self/project reads use canonical record
  ownership, pre-filtered project scope, stable pagination, and concealment.
  They expose no provider reference, secret, balance, or ledger data.
- Callback requires exact actor/link/ServiceIdentity/static row, binding route,
  award, project, instrument, and receipt-state match. Rate limits bind actor
  plus binding, not shared IP alone.
- Reconciliation/rebuild create bounded durable requests and never repair
  immutable contribution, award, or receipt truth.

## Service execution gaps that must be closed

The 22 mappings above cover human/public queries, management requests, the
callback, and generic outbox dispatch. They do not authorize protected feature
handler execution. `workstream.outbox.dispatcher` with `outbox.dispatch` can
only claim, invoke, and finalize events; it cannot transitively receive every
handler's mutation/provider authority.

Before CON-02B/08A/10C protected execution, AUTH and the human must approve
exact ServiceIdentity/ActionId/static-row contracts. CON-08B independently
requires the authenticated callback identity/action/static-row contract:

| Boundary | Discovery candidate identity | Discovery candidate action | Required result |
|---|---|---|---|
| outbox mechanics | `workstream.outbox.dispatcher` | `outbox.dispatch` | exact closed identity and singleton static row |
| outbound fulfillment delivery | `workstream.compensation.delivery` | `compensation.delivery.execute` | independent feature authority; never inherited from dispatcher |
| async compensation reconciliation | `workstream.compensation.reconciler` | `compensation.reconcile.execute` | exact bounded execution action or approved dual-principal evaluator |
| async contribution projection rebuild | `workstream.contribution.projection_rebuilder` | `contribution.projection.rebuild.execute` | exact bounded execution action or approved dual-principal evaluator |
| fulfillment callback | `workstream.compensation.fulfillment_reporter` | `compensation.fulfillment.report` | one approved fixed identity/static row or an explicitly specified closed set |

Candidate strings are not approved identifiers. If AUTH reuses an existing
request ActionId for fixed-service execution, it must specify a closed dual-
principal evaluator and prove human/service isolation. CON must not infer that
design. Each new identity requires closed enum/static-matrix changes, controlled
ActorProfile/ActorIdentityLink provisioning, service_identity constraint
migration custody, AUTH-09E admission, exact cross-service negative tests, and
activation only after hidden behavior merges.

## Upstream review and task actions

Only the stable `task.claim` PermissionId exists on trusted main; there is no
registered task-claim ActionId among the 65 actions. AUTH-PREP, the exact
submitter grant, and the task-owned claim seam precede CON-05A's hidden freeze
participant. CON-05A and task-owned composition must merge first. AUTH-13 then
enumerates/registers the exact task-claim ActionId, integrates its evaluator,
and activates only after the immutable ContributionPolicyVersion freeze and
rollback proof exist.
`review.claim` and `review.decision` are current planned actions; CON-06/07
provide hidden participants, REV supplies canonical composition, and AUTH
activates only after the complete behavior merges.

### Required AUTH follow-up from PR #140

- The current `WS-AUTH-001-13` contract owns future task-claim ActionId
  enumeration/registration, activation, and exact submitter-grant evaluation,
  but it does not yet name the CON-05A TaskAssignment
  ContributionPolicyVersion freeze as a prerequisite. Its executable refresh
  must consume the merged CON-05A manifest and prove task-owned participant
  composition before it registers/activates that action.
- Future CON registration contracts must choose exact `WS-AUTH-001-*`
  activation custodians from complete feature manifests. The removed
  `AUTH_CON_*` planning labels are not approved ActionOwner values.
- `review.claim` activation must consume CON-06 through REV's hidden claim
  composition. PR #140 already states that `review.decision` activation
  requires the merged mandatory CON participant and one rollback-safe REV+CON
  transaction; no additional FinalAcceptance action is needed.

These are upstream AUTH contract gates. CON does not edit AUTH files, register
identifiers, integrate evaluators, or change availability.

AUTH must reconcile all 19 current review actions as one complete activation-
custody transfer under `WS-XINT-001/AUTH_REV_HANDOFF.md`. WS-CON declares only
its two dependencies and must not remove or retain individual REV ActionOwner
members locally. The four proposed additive review actions remain absent until
their own registration contract.

Likewise, the complete 25-action ART transfer belongs to
`WS-XINT-001/AUTH_ART_HANDOFF.md`. WS-CON has no core ART dependency and does not
repeat an eleven-action subset.

## Optional evidence action

If optional contribution-evidence projection is separately approved, one
additional action may be proposed:

```text
artifact.contribution_evidence.binding.create
  -> existing artifact.binding.create
  -> existing workstream.artifact.binding ServiceIdentity
```

AUTH would extend that identity's static row by exactly this action only after a
reviewed ART capability contract exists. This optional action is outside the 22
core proposal and outside release readiness. It cannot be used to authorize
core ContributionRecord creation or reads.

## D11 AdminRole decisions

Before CON-10A/10B registration, the human must choose exact candidates for:

- Project Manager inclusion in project award detail;
- reason-bound Operator delivery recovery in addition to Finance Authority;
- audit read/export role sets.

Any difference from merged AUTH definitions is implemented by AUTH through an
action-owned closed role intersection before grant query. Mixed eligible and
excluded grants select only the eligible grant. CON receives matched decision
evidence and contains no role branch.

## Activation and release proof

AUTH proof must cover planned denial, exactly one custodian per action,
PermissionId parity, evaluator/context completeness, exact human grants,
ServiceIdentity/static-matrix membership, AUTH-09E admission, cross-service
denial, same-token revocation, prepared-handle misuse, transaction-time
revalidation, and decision-evidence failure. Feature proof covers canonical
facts, lifecycle guards, commit/rollback, and no AUTH persistence import.

Startup may fail on closed code/catalogue/static-matrix/evaluator/active-
behavior drift. Runtime and release readiness deny on missing provisioned
service rows. Administrative provisioning remains available.

This handoff changes no AUTH runtime and starts no AUTH or CON chunk.
