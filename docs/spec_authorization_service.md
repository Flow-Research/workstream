# Workstream Authorization Service Specification

## Status And Scope

This is the canonical repository specification for the target Workstream
authorization service. It reconciles the adopted archival WS-AUTH-001 input
with ADR 0006, ADR 0012, the existing `/api/v1` namespace, and current module
boundaries.

The current backend remains on a staged migration path until the owning
WS-AUTH-001 implementation chunks merge. This specification must not be read as
evidence that an unimplemented route or guard already exists.

## Authority Boundaries

The external Identity Issuer owns authentication. Workstream verifies its
tokens and owns product authorization.

| Boundary | Owner | Rule |
|---|---|---|
| Login, passwords, primary sessions, token issuance | External Flow Identity Issuer | Workstream does not implement them. |
| Signature, issuer, audience, time, subject kind, coarse scope | Existing `AuthVerifier` adapter/dependency boundary | Fail closed; pin algorithms and issuer configuration. |
| Actor identity and identity links | `backend/app/modules/actors` | One canonical profile; issuer/subject links are explicit and revocable. |
| Grants, permissions, idempotency, invalidation, decisions | `backend/app/modules/authorization` | Deny by default; no token-role product authority. |
| Resource facts | Owning feature services/repositories | Repositories return domain records; application services compose `ResourceContext`. |
| Review lifecycle | WS-REV-001 | Authorization supplies actors and permissions but does not invent review outcomes. |
| Contribution and compensation | WS-CON-001 | Authorization does not redefine contribution or compensation behavior. |

All public routes use `/api/v1`. The archival short prefix is not an alias.

## Authentication Contract

`VerifiedIssuerToken` contains only verified identity and coarse-access data:

- canonical issuer;
- opaque subject;
- audience;
- issued-at, expiry, optional not-before;
- mandatory token identifier (`jti`);
- subject kind;
- verified coarse scope.

It contains no Workstream product role or permission. Email, display name,
skills, reputation, and relationship metadata are never authorization keys.
During the compatibility period, `/api/v1/auth/me` and actor registration do
not copy issuer email or display name, and those response fields remain null.
Canonical profile metadata is owned by the later actor-profile migration.

Human first access may create a canonical human profile and identity link.
Unknown service subjects, agents, and Spaces are denied without implicit
provisioning. Service actors require explicit pre-provisioning.

## Actor Model

### ActorProfile

`ActorProfile` is the canonical Workstream actor root.

Required concepts:

- UUID identifier;
- kind: human or explicitly provisioned service;
- fixed unique `service_identity` for a service and null for a human;
- status: active, suspended, or deactivated;
- contributor domain for human self-service;
- database-time creation/update and immutable historical attribution.

A profile status is a guard, not a grant. Active humans receive only self
profile capability until an administrative or exact-project grant exists.
For a service, the profile is the stable local principal. Its immutable
`service_identity` selects one closed typed service-action matrix row; it is
never inferred from display data, token claims, issuer, or subject. Profile ID,
service identity, and external credential binding remain separate concepts.

### ActorIdentityLink

An identity link binds one canonical issuer and opaque subject to exactly one
profile. Link state is active or revoked. Raw tokens, provider credentials, and
full provider claims are never persisted.

Existing classified external actor UUIDs may be preserved as profile IDs.
Legacy typed workflow-profile IDs are unrelated and never promoted.

## Grant Model

### Administrative Grants

| Grant | Scope | Purpose |
|---|---|---|
| `access_administrator` | system | Actor, identity-link, and administrative-grant administration. It does not edit the closed permission/action catalog or action availability. |
| `operator` | system | Runtime inspection and explicit recovery operations against canonically resolved resources. |
| `project_manager` | system or exact covered project | Project, task, guide/setup, submission/checker, review, and revision configuration plus contributor grants. It cannot mutate contribution policy or compensation-adapter bindings. System scope covers all projects but remains resource- and lifecycle-guarded; exact-project scope covers only that project. |
| `finance_authority` | system or exact covered project | Contribution policy, compensation-adapter binding, and fulfillment observation owned by WS-CON. |
| `audit_authority` | system or exact covered project | Read-only evidence access and authorized export. |

Administrative grants do not imply contributor capability. An administrator
cannot submit or review by administrative role alone.

### Project Contributor Grants

| Grant | Exact-project capability |
|---|---|
| `submitter` | Minimal project read, task queue read/claim, own submission create/read, own review-chain read. |
| `reviewer` | Minimal project read, review queue/claim/release/decision, submission read for review, review-chain read. |
| `adjudicator` | Minimal project read only; this is shared resource visibility, not adjudication capability. WS-REV must define adjudication resources and AUTH must activate exact actions before adjudication is available. |

Contributor is the umbrella human product term. A contributor may hold
independent exact-project `submitter`, `reviewer`, and `adjudicator` grants.
Holding multiple rows does not bypass separation-of-duties or lifecycle guards.
Celery, checker, setup, and background workers are internal services, not human
product roles.

Grants are immutable history. Issue and revoke target one exact role; one role
never replaces another. Regrant after revocation creates a new immutable row.
No observed token role, typed profile, skill, qualification, or reputation
value creates a grant automatically.

The active model has no `both`, replacement field, replacement event, or
replacement reason. Qualification evidence is bound to the same actor, project,
and exact requested role. One active row is permitted per
actor/project/role. Issue idempotency includes the requested role; revoke derives
the role from the locked grant. Migration `0027` refuses upgrade when obsolete
combined or replacement evidence exists and never converts or deletes those
rows. It replaces current typed and PostgreSQL validators without changing
historical migrations.

## Permission Catalog

AUTH owns the closed PermissionId/ActionId catalog, exact mappings, and action
availability. No human administrative grant edits catalog definitions or moves
an action between `planned` and `active`.

The initial registered catalog includes:

```text
actor.profile.read_self
actor.profile.update_self
actor.profile.read_any
actor.profile.suspend
actor.profile.reactivate
actor.profile.deactivate
actor.identity_link.read
actor.identity_link.revoke
actor.identity_link.reactivate
actor.service.provision

admin_role.read
admin_role.grant
admin_role.revoke

project.create
project.read
project.update
project.archive
project.guide.manage
project.effective_policy.manage
project.task.manage
project.review_policy.manage
project.role_grant.read
project.role_grant.manage

task.queue.read
task.claim
submission.create
submission.read_own
submission.read_for_review

review.queue.read
review.queue.inspect
review.claim
review.release
review.decline_preference
review.decision
review.lease.force_release
review.chain.read
review.queue.override

contribution.read_self
contribution.read_project

compensation.policy.manage
compensation.adapter_binding.manage
compensation.award.read
compensation.delivery.reconcile

operations.status.read
operations.timer.run
operations.reconcile.run
operations.outbox.retry
operations.projection.rebuild
operations.task.start_override
operations.submission_gate.repair
operations.checker.retry

artifact.binding.read
artifact.replica.read
artifact.receipt.read
artifact.verification_job.read
artifact.verification_job.retry
artifact.recovery_attempt.read
artifact.audit.read
artifact.guide_source.ingest
artifact.upload_session.create
artifact.upload_session.read
artifact.upload_item.write
artifact.upload_session.seal
artifact.upload_session.cancel
artifact.upload_session.expire
artifact.binding.create
artifact.verification.execute
artifact.pending_work.scan
artifact.put_attempt.resolve
artifact.guide_source.read
artifact.checker_input.materialize
artifact.checker_output.write

audit.read
audit.export
```

Artifact permissions are deliberately resource- and operation-specific.
`artifact.*.read` permissions do not authorize retry or recovery, human
Operator permissions do not authorize internal execution, and internal service
permissions do not authorize Operator APIs. AUTH-07A owns this closed registry,
AUTH-07B introduces the central kernel, AUTH-08 owns the Operator grant
definitions, AUTH-09A owns the static service-action matrix, AUTH-09B provisions
service ActorProfiles and ActorIdentityLinks, AUTH-09E admits fixed services,
and WS-ART consumes the resulting decisions without registering permissions or
inferring authority. Artifact actions follow AUTH planned
registration, hidden ART behavior/resource composition, then dedicated AUTH
evaluator integration and activation. ART never writes availability. AUTH-12,
AUTH-14, and AUTH-15 are not alternate artifact activation paths.

These are 74 approved `PermissionId` values. `ActionId` values are a separate
closed registry layer and are not included in that permission count. AUTH-05A's
typed and PostgreSQL audit registry accepts the exact historical 49. The three
approved Operator recovery identifiers, 21 artifact identifiers, and
`review.queue.override` are the exact 25 post-`0020` permissions. AUTH-07A adds
their matching typed/SQL audit parity without making them executable.

The closed action registry contains 65 rows after AUTH-09D-A: 15 active actions
and 50 planned rows. AUTH-08 adds seven active administrative definition,
grant-history, issue, revoke, and local-bootstrap actions without adding a
permission. AUTH-09A adds eight planned actor, identity-link, and service
provisioning actions without activating a route; AUTH-09B activates only
`actor.service.provision`, AUTH-09C activates only `actor.profile.read` and
`actor.identity_link.read`, and AUTH-09D-A activates only the three profile
lifecycle actions. The other planned rows cover
three Operator recovery actions, 25 artifact actions, canonical
`submission.create`, and 19 review actions. An action becomes active only when
its feature owner has merged the canonical resource composer, guards, surface or
command declaration, behavior tests, and transaction-local revalidation where
required, and its dedicated AUTH activation custodian has integrated the exact
evaluator and changed availability. Both halves are mandatory; registry or
feature presence alone never grants authority.

The four proposed REV lifecycle actions and
`artifact.review_evidence.binding.create` are not part of the current runtime
registry. Catalogue totals are derived from trusted `main` when each gate runs:
REV registration adds exactly four planned and zero active actions, while the
review-evidence registration adds exactly one planned and zero active action, in
either order. Both retain 74 PermissionIds and stay blocked until complete
feature-owned typed and transaction manifests exist.

AUTH-07B activates `actor.profile.read_self` and `actor.profile.update_self`.
AUTH-08 activates exactly seven administrative actions through migration
`0022`; all other registered actions remain planned.

AUTH-09A registers these exact planned actions through migration `0023`:

| ActionId | PermissionId | Activation owner |
|---|---|---|
| `actor.profile.read` | `actor.profile.read_any` | `WS-AUTH-001-09C` |
| `actor.profile.suspend` | `actor.profile.suspend` | `WS-AUTH-001-09D-A` |
| `actor.profile.reactivate` | `actor.profile.reactivate` | `WS-AUTH-001-09D-A` |
| `actor.profile.deactivate` | `actor.profile.deactivate` | `WS-AUTH-001-09D-A` |
| `actor.identity_link.read` | `actor.identity_link.read` | `WS-AUTH-001-09C` |
| `actor.identity_link.revoke` | `actor.identity_link.revoke` | `WS-AUTH-001-09D-B` |
| `actor.identity_link.reactivate` | `actor.identity_link.reactivate` | `WS-AUTH-001-09D-B` |
| `actor.service.provision` | `actor.service.provision` | `WS-AUTH-001-09B` |

AUTH-09B activates only `actor.service.provision` through the controlled route
described below. AUTH-09C activates only the two bounded actor-registry reads.
AUTH-09D-A activates profile suspend, reactivate, and terminal deactivate. The
two identity-link mutations remain unavailable until AUTH-09D-B supplies their
route, typed resource context, evaluator, guards, transaction proof, and
availability change. AUTH-09A supplies none of those runtime paths.

The submission/review dependency matrix is closed. AUTH-07A registers only the
four stable planned fields shown here; resource facts, candidates, guards, and
hidden behavior remain with the listed feature owner. The current owner values
are planned pre-transfer catalogue state, not permission for a feature chunk to
activate. Before any review action activates, AUTH must transfer activation
custody according to `ACTIVATION_CUSTODY.md` and the reviewed
`.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/AUTH_REV_HANDOFF.md`.

| ActionId | PermissionId | Historical pre-transfer owner value |
|---|---|---|
| `submission.create` | `submission.create` | `WS-AUTH-001-14` |
| `review.queue.read` | `review.queue.read` | `WS-REV-001-05` |
| `review.queue.inspect` | `review.queue.inspect` | `WS-REV-001-05` |
| `review.claim` | `review.claim` | `WS-REV-001-06` |
| `review.release` | `review.release` | `WS-REV-001-06` |
| `review.decline_preference` | `review.decline_preference` | `WS-REV-001-06` |
| `review.preference_expiry.run` | `operations.timer.run` | `WS-REV-001-06` |
| `review.lease_expiry.run` | `operations.timer.run` | `WS-REV-001-06` |
| `review.context.read` | `submission.read_for_review` | `WS-REV-001-07` |
| `review.chain.read` | `review.chain.read` | `WS-REV-001-07` |
| `review.finding_evidence.ingest` | `review.decision` | `WS-REV-001-07` |
| `review.decision` | `review.decision` | `WS-REV-001-08` |
| `review.finding_response_evidence.ingest` | `submission.create` | `WS-REV-001-09A` |
| `review.lease.force_release` | `review.lease.force_release` | `WS-REV-001-11` |
| `review.queue.routing.override` | `review.queue.override` | `WS-REV-001-11` |
| `review.queue.routing.correct` | `review.queue.override` | `WS-REV-001-11` |
| `review.queue.close` | `review.queue.override` | `WS-REV-001-11` |
| `review.reconcile.run` | `operations.reconcile.run` | `WS-REV-001-11` |
| `review.artifact_reference.reconcile` | `operations.reconcile.run` | `WS-REV-001-12` |
| `review.projection.rebuild` | `operations.projection.rebuild` | `WS-REV-001-12` |

Initial and revision submission use the same `submission.create` action,
permission, and route. Revision preparation is an internal participant and
lifecycle guard of that command; no `submission.revise` or revision-prepare
action exists. Finding and finding-response evidence intake are distinct
protected commands mapped to existing permissions. The only new permission is
`review.queue.override`.

Artifact verification recovery remains the existing
`artifact.verification_job.retry` action through the ART-owned
`ArtifactOperatorRecoveryPort`; no `artifact_recovery.request` permission is
registered. Shared outbox dispatch/retry remains owned by the shared-outbox
subsystem and is not represented as a REV-owned projection action.

Migration `0021` is availability-neutral. PostgreSQL enforces the closed
ActionId set, authorization-decision event shape, exact ActionId-to-PermissionId
mapping, and the requirement that every post-`0018` permission carry a mapped
action. Typed catalogue validation separately rejects allowed evidence until the
dedicated AUTH activation custodian changes an action from `planned` to `active`
after merged feature behavior proof.

The paired artifact hidden-behavior matrix is closed:

| Resource-owning WS-ART chunk | Hidden actions/resources implemented by that chunk |
|---|---|
| `WS-ART-001-02D` | Operator binding/replica/receipt/verification-job/recovery-attempt/audit reads; the operations-domain `operations.artifact_storage_admission.read` action mapped to `operations.status.read`; verification retry; `artifact.verification.execute`; `artifact.pending_work.scan`; and `artifact.put_attempt.resolve` |
| `WS-ART-001-03` | `artifact.guide_source.ingest`, `artifact.guide_source.read`, and `artifact.guide_source.binding.create` mapped to `artifact.binding.create` |
| `WS-ART-001-04A` | upload-session create/read/seal/cancel/expire and upload-item write |
| `WS-ART-001-04B` | `artifact.pre_submit.checker_input.materialize` mapped to `artifact.checker_input.materialize` |
| `WS-ART-001-05` | `artifact.submission.binding.create` mapped to `artifact.binding.create` |
| `WS-ART-001-06A` | `artifact.post_submit.checker_input.materialize` mapped to `artifact.checker_input.materialize` |
| `WS-ART-001-06B` | `artifact.checker_output.write` and `artifact.checker_output.binding.create` mapped to `artifact.binding.create` using the checker-run resource |

Every row requires AUTH-07A's registry and AUTH-07B's kernel first. A row with an Operator principal
also requires its AUTH-08 grant definition; a row with a fixed service
principal also requires AUTH-09A's static matrix, AUTH-09B's provisioned service
ActorProfile and ActorIdentityLink, and AUTH-09E fixed service runtime
admission. After the named ART behavior merges, the dedicated AUTH custodian
integrates and activates the exact evaluator. Feature code receives centralized
decisions; it never queries grants, constructs permission identifiers
dynamically, or changes availability.

The following table is the single source of truth for artifact ActionId-to-
PermissionId mappings, principal/resource facts, and ART hidden-behavior
ownership. AUTH-07A registers only each row's stable `ActionId`, approved
  `PermissionId`, historical pre-transfer owner value, and `planned`
availability. Its principal-class and canonical-resource columns are not AUTH
registry fields and are not executable authority; the owning WS-ART chunk adopts
them with its hidden canonical resource composer, guards, surface declaration,
and behavior tests. The complete AUTH activation-custody transfer is separately
canonical in
`.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/AUTH_ART_HANDOFF.md`.
A mapping is not a permission alias.

| ActionId | PermissionId | Principal class | Canonical resource | Resource-owning WS-ART chunk |
|---|---|---|---|---|
| `artifact.binding.read` | `artifact.binding.read` | Operator | artifact binding | `02D` |
| `artifact.replica.read` | `artifact.replica.read` | Operator | artifact replica | `02D` |
| `artifact.receipt.read` | `artifact.receipt.read` | Operator | artifact receipt | `02D` |
| `artifact.verification_job.read` | `artifact.verification_job.read` | Operator | verification job | `02D` |
| `artifact.verification_job.retry` | `artifact.verification_job.retry` | Operator | exhausted verification job | `02D` |
| `artifact.recovery_attempt.read` | `artifact.recovery_attempt.read` | Operator | recovery attempt | `02D` |
| `artifact.audit.read` | `artifact.audit.read` | Operator | artifact audit scope | `02D` |
| `operations.artifact_storage_admission.read` | `operations.status.read` | Operator | deployment artifact-storage namespace | `02D` |
| `artifact.guide_source.ingest` | `artifact.guide_source.ingest` | authorized project actor | guide-source snapshot item | `03` |
| `artifact.guide_source.read` | `artifact.guide_source.read` | fixed guide-reader service | guide-source snapshot item | `03` |
| `artifact.upload_session.create` | `artifact.upload_session.create` | assigned contributor | task | `04A` |
| `artifact.upload_session.read` | `artifact.upload_session.read` | assigned contributor | upload session | `04A` |
| `artifact.upload_item.write` | `artifact.upload_item.write` | assigned contributor | upload item | `04A` |
| `artifact.upload_session.seal` | `artifact.upload_session.seal` | assigned contributor | upload session | `04A` |
| `artifact.upload_session.cancel` | `artifact.upload_session.cancel` | assigned contributor | upload session | `04A` |
| `artifact.upload_session.expire` | `artifact.upload_session.expire` | fixed scheduler service | upload session | `04A` |
| `artifact.guide_source.binding.create` | `artifact.binding.create` | fixed binding service | guide-source snapshot item | `03` |
| `artifact.submission.binding.create` | `artifact.binding.create` | fixed binding service | submission | `05` |
| `artifact.checker_output.binding.create` | `artifact.binding.create` | fixed binding service | checker run | `06B` |
| `artifact.verification.execute` | `artifact.verification.execute` | fixed verifier service | verification job | `02D` |
| `artifact.pending_work.scan` | `artifact.pending_work.scan` | fixed scheduler service | system pending-work scope | `02D` |
| `artifact.put_attempt.resolve` | `artifact.put_attempt.resolve` | fixed put-resolver service | put attempt | `02D` |
| `artifact.pre_submit.checker_input.materialize` | `artifact.checker_input.materialize` | fixed materializer service | sealed upload session and task | `04B` |
| `artifact.post_submit.checker_input.materialize` | `artifact.checker_input.materialize` | fixed materializer service | checker run and immutable bindings | `06A` |
| `artifact.checker_output.write` | `artifact.checker_output.write` | fixed checker-output service | checker run | `06B` |

The fixed internal service identities and their complete artifact action sets
are also closed:

| Service identity | Allowed artifact actions |
|---|---|
| `workstream.artifact.verifier` | `artifact.verification.execute` |
| `workstream.artifact.put_resolver` | `artifact.put_attempt.resolve` |
| `workstream.artifact.scheduler` | `artifact.pending_work.scan`, `artifact.upload_session.expire` |
| `workstream.artifact.binding` | `artifact.guide_source.binding.create`, `artifact.submission.binding.create`, `artifact.checker_output.binding.create` |
| `workstream.artifact.guide_reader` | `artifact.guide_source.read` |
| `workstream.artifact.materializer` | `artifact.pre_submit.checker_input.materialize`, `artifact.post_submit.checker_input.materialize` |
| `workstream.artifact.checker_output` | `artifact.checker_output.write` |

AUTH-09B lets a system Access Administrator bind an exact configured-issuer
subject with no leading or trailing whitespace to one of these fixed identities
through `POST /api/v1/service-actors`. Accepted subject bytes are preserved
without normalization.
It creates the service ActorProfile and ActorIdentityLink, but creates no role,
grant, assignment, or executable service authority. A newly provisioned service
profile has null `last_seen_at`, and its link has null `last_verified_at` until
AUTH-09E verifies and admits that exact service token. The service-action matrix
is typed code, not a database assignment or grant table. Its rows remain inert
while their actions are planned. After the ART execution behavior merges, the
dedicated AUTH activation custodian integrates the evaluator and changes only
the exact action to active. Composition startup proves registry, service actor,
matrix row, action, and PermissionId parity and fails closed on missing or extra
matrix membership. Negative authorization tests prove each service identity is
denied every artifact action outside its row. Human authorization remains
attached to the initiating product command; an internal service identity never
inherits a human grant or role.

Adding a permission requires a specification/ADR update and human approval.
Routers cannot invent identifiers or evaluate grant unions.

### Action And Resource Registration

The permission catalog is consumed through a closed, typed action registry.
Each active action definition has its own stable `ActionId` and binds one
approved `PermissionId` to:

- one canonical authorization target resource type;
- the rule for resolving that target, including the existing parent or `system`
  target used when the requested operation creates a new resource;
- the allowed human or service principal class and authority-candidate sources;
- registered global, resource, ownership, assignment, separation-of-duties, and
  lifecycle guards; and
- the closed, typed resource facts required by each guard; and
- whether authority must be revalidated inside the committing transaction.

Multiple closed actions may map to one approved broad permission while having
different canonical targets and guards. For example, create and update actions
may share an approved management permission but target an existing parent and
an existing child respectively. Routes declare `ActionId`, never an arbitrary
permission/target pair. Splitting a broad permission into new permission tokens
still requires the separate approval and migration rule above.

The registry does not own domain persistence or state transitions. Feature
repositories return their domain records, and feature application services or
feature-owned loaders compose the bounded `ResourceContext`. Loader
implementations may be registered at the application composition root, but the
authorization module must not duplicate feature queries or import a parallel
resource repository. Resource contexts use closed per-resource variants rather
than a free-form attribute bag. Registration rejects undeclared facts, and
authorization fails closed when a required fact is absent or has the wrong
type. Request bodies, query values, and path combinations remain untrusted
hints; canonical parent, project, owner, assignment, and state facts come from
PostgreSQL.

Each protected FastAPI route and asynchronous command declares one primary
registered action. That declaration selects the authorization target and
mandatory guards; it does not replace domain invariants or permit a route-local
secondary policy. Internal jobs declare fixed Workstream service authority and
never serialize a human bearer token as executable authority. Collection
actions authorize and filter against their canonical parent scope before
counts, cursors, facets, or distinct values are computed.

Registration and completeness are staged with the approved chunk map. Chunk
07A introduces the identifiers and planned registry; 07B introduces the kernel
and first active self-actions. Reserved action metadata contains only the
stable `ActionId`, approved `PermissionId`, owning specification/chunk, and
`planned` availability; it is not executable and does not predefine a
foreign-domain target, facts, or guards. Every route-owning chunk from 07B
through 15 supplies hidden behavior, feature-owned resource composition,
surface declarations, and behavior proof while its action remains planned and
fails closed. Only the action's dedicated AUTH activation custodian may promote
it to active after integrating the evaluator and verifying that proof. Each
feature chunk generates a manifest-delta proof for every surface it prepares;
the matching AUTH activation chunk records the availability delta. Chunk 16
aggregates and verifies the complete route/command manifest rather than first
discovering missing declarations there.
Resources and transitions owned by WS-REV, WS-CON, or the artifact-storage
specification are not invented by AUTH; their owning specification must first
approve the resource facts and operation before a corresponding permission is
added under the approval rule above.

## Authorization Algorithm

For every protected operation:

1. Verify the external token through the existing verifier boundary.
2. Resolve the canonical identity link and actor profile without preempting the
   action's lifecycle guards.
3. Build request-scoped `AuthorizationContext` without token-role authority.
4. Load the canonical resource through its owning repository/service.
5. Compose `ResourceContext` in the application service.
6. Load active candidate grants using database time.
7. Expand only registered permission candidates compatible with grant scope.
8. Apply actor, exact-project, ownership, assignment, separation-of-duties,
   task-ban, and lifecycle guards.
9. For sensitive mutations, revalidate authority inside the same transaction
   immediately before commit.
10. Return allow or a stable denial code without leaking hidden resources.

Authorization decisions are request-scoped and are not cached across requests.
Each decision carries a bounded SHA-256 digest of its complete typed resource
context so feature code cannot reuse it with substituted role, scope, target,
or replay facts. List filtering occurs before counts and pagination cursors.

Sensitive mutations use the prepared protocol instead of evaluating final
authority against unlocked feature facts:

```text
AUTH locks AuthorityControl first when final-admin safety applies
-> AUTH orders principals by ActorProfile ID
-> human: ActorProfile -> exact ActorIdentityLink -> exact matched grant
-> service: ActorProfile -> exact ActorIdentityLink -> code-owned validations
-> AUTH creates one internal non-Pydantic PreparedAuthorizationHandle bound to
   session, action, actor reference, idempotency key, and request digest
-> feature locks its canonical rows and recomposes final typed facts
-> AUTH consumes the handle, evaluates once, and stages decision evidence
-> feature participants flush
-> route or service command commits once
```

Service identity, static service-action matrix membership, and action
availability are immutable code-owned validations after the service profile and
link locks; they are not database rows or lock targets. Existing actor-self,
administrative, and lifecycle mutations must use the same authority-row order
before any prepared consumer ships.

The handle is single-use, nonserializable, and never a route schema or caller
input. Consumption matches the exact session, action, actor reference kind,
actor reference, idempotency key, and request digest before feature mutation.
Reuse, same-session/action cross-actor or cross-request substitution, authority
loss, evidence failure, participant failure, cancellation, or commit failure
leaves no feature mutation or partial authority evidence. Reads continue to use
request-scoped `require()`. AUTH never imports feature repositories, and
dependency teardown never commits shared feature work.
Crossed PostgreSQL tests cover PREP against link revocation, actor suspension or
deactivation, exact grant revocation, and final-admin mutation.

For the two active self actions, the default human authority source is
`actor_self`; token roles and client-supplied permissions never enter the
context. Self-read requires an active link and an active or suspended actor.
Self-update additionally locks the exact link followed by its linked profile,
rebuilds current context inside the caller transaction, and requires an active
actor plus a non-empty subset of `display_name` and `contact_email`. Revoked
links, deactivated actors, and suspended updates deny in that order. Planned
and unknown actions deny as `permission_not_granted` at public boundaries, and
a system resource grants no implicit authority.

`AuthorizationService.require(action_id, typed_resource_context)` has exactly
those two method arguments because the request context, caller-owned
`AsyncSession`, and actor-self revalidator are constructor-bound. The service
stages one bounded decision event and never commits. A denied mutation rolls
back first, then restages the unchanged denial in a clean transaction so no
business mutation can share a denial commit.

`AuthorizationDecision` carries the stable `ActionId` in addition to permission,
resource, scope, matched authority, and denial information. The action identifier
is included in bounded logs/metrics and every action-based allowed or denied
authority event emitted by AUTH-07B or a later chunk. AUTH-07A adds nullable
historical storage and exact typed/SQL registry parity; legacy rows remain null,
while new AUTH-07B-or-later action-based decision events must contain a
registered identifier. A
new action identifier requires the same approved typed/PostgreSQL registry and
migration treatment as a permission.

## Separation And Recovery Rules

- An actor cannot grant or revoke their own authority through an administrative
  grant operation.
- A submitter cannot act as the sole reviewer of their own work.
- Project Manager authority is limited to its grant scope. A system-scoped
  Project Manager covers all projects but remains subject to resource and
  lifecycle guards; an exact-project grant covers only that project. Only a
  system-scoped Project Manager may create a project because no project scope
  exists before creation.
- Administrative roles alone cannot claim contributor work, submit, or review.
- Operator recovery is distinct from Project Manager management.
- `operations.task.start_override`,
  `operations.submission_gate.repair`, and `operations.checker.retry` require an
  exact reason, canonical resource scope, matched permission/grant, and
  append-only evidence.
- Recovery cannot erase checker evidence, mutate immutable submissions, create
  a human review decision, rewrite contribution history, or bypass compensation
  guards.
- `review.lease.force_release` is governed by WS-REV-001.

## System Work

Internal system workers use fixed Workstream system principals with explicit
registered system permissions. They never receive fabricated human grants.
Serialized requester identity is provenance only. Actor-attributed jobs reload
current actor/link/grant state before committing.

Fixed service callers use a dedicated AUTH service-admission path. It resolves
the verified service subject to one active identity link and service
ActorProfile, validates the immutable `service_identity`, and selects only that
identity's exact static ActionId row. It never enters human provisioning or
human grant evaluation. Feature actions remain unavailable until their owning
feature supplies canonical resource facts, guards, hidden behavior, and proof
and AUTH separately activates them.

New fixed services are added only after the owning feature publishes an exact
identity-to-ActionId manifest. AUTH then owns one closed enum/constraint/matrix
extension, controlled provisioning, admission reuse, and all-pairs
cross-service denial. REV timer, expiry, reconciliation, projection,
artifact-reference, and release-control identities are not pre-created, and no
catch-all review service exists.

## Bootstrap And Final-Administrator Safety

The first Access Administrator is created through a local management command
for an existing active human. There is no public bootstrap endpoint or shared
bootstrap bearer secret.

Bootstrap locks `AuthorityControl(id = 1) FOR UPDATE`, validates its incomplete
irreversible state and the target's active human profile and identity link, and
writes the initial grant, completed control state, and audit event atomically.
Every later or losing bootstrap attempt returns a stable audited conflict.

Bootstrap and every grant/profile/link operation that could remove the final
effective Access Administrator use the same row lock and transaction-local
effective count.

## Revocation And Invalidation

Suspension, deactivation, identity-link revocation, and grant revocation take
effect on the next request and on the next sensitive transaction recheck. Each
mutation writes an invalidation event atomically with state and evidence.
Profile reactivation writes the inverse `effective=false -> effective=true`
component invalidation. That fact describes the profile only: a revoked link,
missing grant, or unadmitted fixed service can still make the actor ineffective.

Assignment reconciliation preserves immutable work history. A revoked actor's
ordinary claimed/in-progress assignment may be released by the owning later
chunk. A `needs_revision` task retains a durable revision obligation and cannot
be returned as ordinary ready work.

Project-role invalidation is exact-role-specific. Submitter revocation alone can
enter task-assignment reconciliation. Reviewer revocation creates only the
REV-owned review obligation; adjudicator invalidation remains dormant until its
lifecycle is enabled. Revoking any one project role leaves the other roles and
all AdminRoleGrants unchanged. Consumers verify the cause event, grant ID,
actor, project, and role before changing product state.

## Idempotency And Authority Evidence

Authority-changing APIs require canonical request hashing and idempotency keys.
An exact replay returns the committed result; a mismatched replay is rejected.

Authority events are append-only and include, when applicable:

- schema/event version;
- request and correlation identifiers;
- acting and target actor references;
- registered action identifier for action-based decisions;
- matched grant and permission;
- exact project/resource reference;
- required reason;
- idempotency key;
- bounded before/after state;
- database time.

Business state, idempotency result, authority event, and invalidation event
commit in one `AsyncSession` transaction. Missing evidence is not backfilled
later. Administrative mutation and post-allow denial evidence derives its
request and correlation identifiers from the exact authorization decision;
feature callers cannot supply alternate evidence identifiers.
Administrative issue/revoke also recomputes the bounded reason digest before
any state or evidence write and rejects cross-wired reason text.

## API Families

Canonical route families use `/api/v1`:

```text
GET|PATCH /api/v1/actors/me
GET /api/v1/authorization/permissions
GET /api/v1/authorization/admin-role-definitions
GET /api/v1/actors/{actor_profile_id}
POST /api/v1/actors/{actor_profile_id}/suspend|reactivate|deactivate
GET /api/v1/actors/{actor_profile_id}/identity-links
POST /api/v1/actor-identity-links/{link_id}/revoke|reactivate
POST /api/v1/service-actors

POST|GET /api/v1/admin-role-grants
GET /api/v1/actors/{actor_profile_id}/admin-role-grants
POST /api/v1/admin-role-grants/{grant_id}/revoke

POST|GET /api/v1/projects/{project_id}/role-grants
GET /api/v1/projects/{project_id}/role-grants/{grant_id}
POST /api/v1/projects/{project_id}/role-grants/{grant_id}/revoke
```

Exact request/response/error contracts are introduced by their owning chunks.
Grant issue input may select a registered role and compatible scope, but that
selection is only the requested grant; it never supplies the caller's authority.

AUTH-07B cuts existing `GET|PATCH /api/v1/actors/me` behavior over to the
kernel. AUTH-08 activates the two definition reads, scoped grant/history reads,
issue/revoke APIs, and local bootstrap command. AUTH-09C activates exact actor
and identity-link reads for effective system Access Administrator or Audit
Authority grants. AUTH-09D-A activates the three profile lifecycle routes for
effective system Access Administrators only. The two identity-link lifecycle
routes remain unavailable until AUTH-09D-B; the project-role route family also
remains planned. Project-scoped
`GET /api/v1/actors/me/authorization-context` begins in AUTH-10 after
exact-project grant and canonical project capability composition exists.

## Migration And Compatibility

The implementation order is fixed by the WS-AUTH-001 chunk map:

1. `WS-AUTH-001-01`: canonical docs and ADR;
2. `WS-AUTH-001-02`: verified issuer token/JWKS boundary;
3. `WS-AUTH-001-03`: legacy actor classification;
4. `WS-AUTH-001-04`: request/error/rate controls;
5. `WS-AUTH-001-05`: authority evidence/idempotency;
6. `WS-AUTH-001-06`: canonical actor/link migration;
7. `WS-AUTH-001-07`: authorization kernel;
8. `WS-AUTH-001-08`: bootstrap/admin grants;
9. `WS-AUTH-001-09A`: fixed service identity and static matrix foundation;
10. `WS-AUTH-001-09B`: controlled service ActorProfile/ActorIdentityLink
    provisioning with an unverified service link until AUTH-09E verifies the
    service token;
11. `WS-AUTH-001-09C`: actor and identity-link administrative reads;
12. `WS-AUTH-001-09D-A`: lifecycle evidence repair and actor-profile suspend,
    reactivate, and terminal deactivate;
13. `WS-AUTH-001-09D-B`: identity-link revoke/reactivate and mixed lifecycle
    race closure;
14. `WS-AUTH-001-09E`: fixed service runtime admission without human grant
    evaluation or feature action activation;
15. `WS-AUTH-001-ART-CUSTODY` and `WS-AUTH-001-REV-CUSTODY`:
    availability-neutral transfer to exact AUTH activation owners;
16. `WS-AUTH-001-PREP`: prepared mutation authorization protocol;
17. `WS-AUTH-001-10`: independent project contributor grants;
18. `WS-AUTH-001-11` through `WS-AUTH-001-14`: complete resource-family
    cutovers;
19. `WS-AUTH-001-15`: obsolete authority removal and scanner enforcement;
20. `WS-AUTH-001-16`: conformance, observability, concurrency, and live API
    proof.

No implementation may add a compatibility alias, fallback authority source,
dual route, or translation into canonical grants. The remaining explicitly
enumerated legacy paths are removal-only: their allowlist may only shrink, and
their assigned cutover must delete them rather than preserve an alternate path.
No implementation chunk may create a second canonical actor root, verifier
hierarchy, audit ledger, unit-of-work abstraction, or authorization engine.

## Error And Privacy Contract

Errors use a stable envelope and denial codes. They do not contain raw
exceptions, tokens, full claims, secrets, JWKS material, private artifact
content, or unnecessary personal data. Unauthorized resources are concealed
where existence itself is sensitive.

First access and administrative mutations are rate-controlled through
Postgres-backed fail-closed controls before their public APIs become available.

## Conformance Requirements

Each owning chunk must prove:

- allow and deny cases for every permission path;
- migrated surfaces derive product authority only from local grants and guards;
- cross-project and concealed-resource behavior;
- immediate same-token revocation;
- state/grant/link and final-administrator concurrency;
- idempotent exact replay and mismatched replay rejection;
- append-only allowed and denied evidence;
- preserved current intake lifecycle through the full backend suite and API
  contract drill;
- no test skip, xfail, assertion weakening, dependency override, fabricated
  authorization context, or direct grant insertion as product proof.
- every protected route and asynchronous command migrated by that chunk has one
  primary registered action declaration, a canonical target derived through its
  owning feature boundary, and allow/deny tests for its mandatory guards.

Final chunk 16 proof includes a generated `/api/v1` route and asynchronous
command manifest. It fails closed on an unknown permission or resource type, a
duplicate or missing primary declaration, or an unregistered guard. The manifest
is conformance evidence, not a second policy source.

Each activating chunk must also prove its authorization-subsystem changes at or
above 90 percent coverage and preserve the repository-wide 78 percent baseline.

The final live drill must operate through supported APIs/commands without
direct database authority edits.

## Precedence And Non-Goals

This specification and ADR 0012 supersede active token-role and typed-profile
authorization claims. ADR 0006 still controls authentication ownership.
WS-REV-001 and WS-CON-001 control their own product behavior.

This specification does not add Workstream login, implement runtime code,
change review decision values, define contribution/compensation behavior, add a
frontend, enable blockchain settlement, add source adapters, automate routing,
or create an agent workspace.
