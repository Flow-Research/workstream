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
the role from the locked grant. Migration `0031` refuses upgrade when obsolete
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
project.setup_diagnostic.read
project.effective_policy.read
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
artifact.binding.create
artifact.verification.execute
artifact.pending_work.scan
artifact.put_attempt.resolve
artifact.guide_source.read
artifact.checker_input.materialize
artifact.checker_output.write
artifact.review_packet.materialize

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

These are 71 approved `PermissionId` values. `ActionId` values are a separate
closed registry layer and are not included in that permission count. AUTH-05A's
typed and PostgreSQL audit registry accepts the exact historical 49. The three
approved Operator recovery identifiers, 16 artifact identifiers,
`review.queue.override`, and the two AUTH-11A read-only project inspection
permissions are the exact 22 post-`0020` permissions. AUTH-07A, AUTH-11A, and
WS-XINT-002-01 add
their matching typed/SQL audit parity without making them executable.

The closed action registry contained 78 rows after AUTH-11C2: 37 active actions
and 41 planned rows before AUTH-12A. AUTH-12A added eighteen planned
project-mutation rows, producing the historical 96-row state of 37 active and
59 planned. Later project-mutation and ART activation chunks advanced the
pre-02C state to 45 active and 51 planned. WS-XINT-003-02C adds four planned
REV rows, and AUTH-12E activates three existing rows, producing the current
100-row state of 48 active and 52 planned.
AUTH-10A added five project-role read/manage rows;
AUTH-10B owns and activates the three reads, while AUTH-10C owns and activates
the two reason-bound, idempotent project-role mutations. AUTH-11A adds eleven
project identity and actor-context read rows: two are active under 11B, three
setup-diagnostic and three draft/effective-policy diagnostic reads are active
under 11C1, and three current effective-policy and active-guide reads are active
under 11C2.
AUTH-08 adds seven
active administrative definition,
grant-history, issue, revoke, and local-bootstrap actions without adding a
permission. AUTH-09A adds eight planned actor, identity-link, and service
provisioning actions without activating a route; AUTH-09B activates only
`actor.service.provision`, AUTH-09C activates only `actor.profile.read` and
`actor.identity_link.read`, AUTH-09D-A activates the three profile lifecycle
actions, and AUTH-09D-B activates the two identity-link lifecycle actions. The
other registry rows cover three planned Operator recovery actions and the ART
catalogue: 16 planned, three active foundation-service actions, active
`artifact.guide_source.ingest`, and active fixed-service guide binding/read;
the remaining rows cover canonical
`submission.create`, and 23 review actions. An action becomes active only when
its feature owner has merged the canonical resource composer, guards, surface or
command declaration, behavior tests, and transaction-local revalidation where
required, and its dedicated AUTH activation custodian has integrated the exact
evaluator and changed availability. Both halves are mandatory; registry or
feature presence alone never grants authority.

WS-XINT-003-02C registers the four approved REV recovery/lifecycle actions as
planned and unavailable. `artifact.review_evidence.binding.create` is also
registered but planned and unavailable. Registration adds no evaluator, route,
job, principal row, or lifecycle authority; activation remains blocked until
complete feature-owned typed and transaction manifests exist.

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
AUTH-09D-A profile lifecycle activation is complemented by AUTH-09D-B, which
activates exact identity-link revoke and reactivate behavior and their
route, typed resource context, evaluator, guards, transaction proof, and
availability change. AUTH-09A supplies none of those runtime paths.

The submission/review dependency matrix is closed. AUTH-07A registers only the
stable planned fields shown here; resource facts, candidates, guards, and
hidden behavior remain with REV. `WS-AUTH-001-REV-CUSTODY` has replaced only
the 19 historical REV owner values with the exact AUTH activation custodians
below. Mappings and planned availability are unchanged, and the custodian
labels grant no reviewer, Operator, or service authority. Before any review
action activates, its dedicated AUTH custodian must integrate the complete
feature proof according to `ACTIVATION_CUSTODY.md` and the reviewed
`.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/AUTH_REV_HANDOFF.md`.

The AUTH-REV table immediately below is retained as runtime catalogue history.
For all future work, the canonical planning custody, principals, resource
families, fixed identities, and exact XINT-003 waves are in
`.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/ACTION_CUSTODY.md`.
Chunk 01 changes no runtime owner or availability.

| AUTH activation custodian | Exact planned ActionIds |
|---|---|
| `WS-AUTH-001-REV-05` | `review.queue.read`, `review.queue.inspect` |
| `WS-AUTH-001-REV-06` | `review.claim`, `review.release`, `review.decline_preference`, `review.preference_expiry.run`, `review.lease_expiry.run` |
| `WS-AUTH-001-REV-07` | `review.context.read`, `review.chain.read`, `review.finding_evidence.ingest` |
| `WS-AUTH-001-REV-08` | `review.decision` |
| `WS-AUTH-001-REV-09A` | `review.finding_response_evidence.ingest` |
| `WS-AUTH-001-REV-11` | `review.lease.force_release`, `review.queue.routing.override`, `review.queue.routing.correct`, `review.queue.close`, `review.reconcile.run` |
| `WS-AUTH-001-REV-12` | `review.artifact_reference.reconcile`, `review.projection.rebuild` |
| `WS-XINT-003-08A` | `review.revision_context.repair`, `review.revision_obligation.close`, `review.revision_context.legacy_close` |
| `WS-XINT-003-08B` | `review.lifecycle.activation.manage` |

The first seven rows preserve the trusted pre-WS-XINT-003-02C custody baseline.
Those 19 actions remain planned and unavailable, while 02C registers the four approved REV
recovery/lifecycle actions under XINT-003-08A/08B custody. The delivery path is
front-loaded `WS-XINT-003-02C` unavailable catalogue/principal/matrix readiness
followed by `WS-XINT-003-02D` closed PREP/read contract readiness. Neither wave
implements REV behavior or activates a lifecycle action; later XINT activation
uses the canonical custody map and exact merged REV proof.

| ActionId | PermissionId | AUTH activation custodian |
|---|---|---|
| `submission.create` | `submission.create` | `WS-AUTH-001-14` |
| `review.queue.read` | `review.queue.read` | `WS-AUTH-001-REV-05` |
| `review.queue.inspect` | `review.queue.inspect` | `WS-AUTH-001-REV-05` |
| `review.claim` | `review.claim` | `WS-AUTH-001-REV-06` |
| `review.release` | `review.release` | `WS-AUTH-001-REV-06` |
| `review.decline_preference` | `review.decline_preference` | `WS-AUTH-001-REV-06` |
| `review.preference_expiry.run` | `operations.timer.run` | `WS-AUTH-001-REV-06` |
| `review.lease_expiry.run` | `operations.timer.run` | `WS-AUTH-001-REV-06` |
| `review.context.read` | `submission.read_for_review` | `WS-AUTH-001-REV-07` |
| `review.chain.read` | `review.chain.read` | `WS-AUTH-001-REV-07` |
| `review.finding_evidence.ingest` | `review.decision` | `WS-AUTH-001-REV-07` |
| `review.decision` | `review.decision` | `WS-AUTH-001-REV-08` |
| `review.finding_response_evidence.ingest` | `submission.create` | `WS-AUTH-001-REV-09A` |
| `review.lease.force_release` | `review.lease.force_release` | `WS-AUTH-001-REV-11` |
| `review.queue.routing.override` | `review.queue.override` | `WS-AUTH-001-REV-11` |
| `review.queue.routing.correct` | `review.queue.override` | `WS-AUTH-001-REV-11` |
| `review.queue.close` | `review.queue.override` | `WS-AUTH-001-REV-11` |
| `review.reconcile.run` | `operations.reconcile.run` | `WS-AUTH-001-REV-11` |
| `review.artifact_reference.reconcile` | `operations.reconcile.run` | `WS-AUTH-001-REV-12` |
| `review.projection.rebuild` | `operations.projection.rebuild` | `WS-AUTH-001-REV-12` |
| `review.revision_context.repair` | `project.task.manage` | `WS-XINT-003-08A` |
| `review.revision_obligation.close` | `project.task.manage` | `WS-XINT-003-08A` |
| `review.revision_context.legacy_close` | `operations.reconcile.run` | `WS-XINT-003-08A` |
| `review.lifecycle.activation.manage` | `operations.reconcile.run` | `WS-XINT-003-08B` |

### REV integration contracts

`WS-XINT-003-02D` publishes the complete inert REV authorization manifest in
`app.modules.authorization.review_contracts`. Every registered `review.*`
ActionId maps to one strict typed resource family or, for the two unapproved
evidence-upload actions, to explicit `unsupported_future_intent`. Shared
families retain exact action discriminators; fixed-service contracts bind the
exact service identity and server-derived execution mode. In particular, the
two services sharing `review.reconcile.run` cannot exchange modes.

These frozen scalar models carry no ORM rows, bytes, provider values, callback,
or prepared handle. Publishing them changes no action availability and adds no
evaluator. Reads continue through request-scoped authorization. Mutations and
service commands later use the existing opaque, process-local, transaction-
bound `PreparedAuthorizationHandle`; REV locks and composes canonical facts,
while the exact activation wave installs the corresponding AUTH evaluator.
XINT-002 packet, evidence-binding, and revision-submission actions are external
handoff references only and are not redefined by this manifest.

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
| `WS-ART-001-03` | Hidden guide behavior for `artifact.guide_source.ingest -> artifact.guide_source.ingest`, `artifact.guide_source.read -> artifact.guide_source.read`, and `artifact.guide_source.binding.create -> artifact.binding.create`; AUTH activation custody is split between WS-XINT-002-04A and 04B below |
| `WS-ART-001-04A` historical baseline | the former multi-step upload authority had no route/command and is deleted from the live catalogue by WS-XINT-002-01 without compatibility aliases |
| `WS-ART-001-04A1` through `04C2` | one hidden `artifact.submission_bundle.prepare` surface mapped to `submission.create`; 04B1-04B3 implement the sole catalogue/materialization/evidence path, XINT-002-06A activates its fixed pre-submit materializer before 04C1, and the contributor action remains unavailable until complete 04C2 evidence and WS-XINT-002-05A; 05B removes the frozen legacy precheck only when admission-backed Submission becomes authoritative |
| `WS-ART-001-04B2` and `04B3` | hidden `artifact.pre_submit.checker_input.materialize` resource/guard usage mapped to `artifact.checker_input.materialize`; 04B2 owns exact sealed materialization and 04B3 consumes it in the complete effective plan |
| `WS-ART-001-05` | `artifact.submission.binding.create` mapped to `artifact.binding.create` |
| `WS-ART-001-06A` | `artifact.post_submit.checker_input.materialize` mapped to `artifact.checker_input.materialize` |
| `WS-ART-001-06B` | `artifact.checker_output.write` mapped to `artifact.checker_output.write`; `artifact.checker_output.binding.create` mapped to `artifact.binding.create`, both using the checker-run resource |

WS-XINT-002-01 deletes the former multi-step authority and registers planned
`artifact.submission_bundle.prepare -> submission.create`. No ART implementation
may execute that ActionId while it remains planned. The mandatory order is
ART-04A1 -> 04A2 -> 04A3 -> PLAN4 -> PLAN5 -> 04B1 -> 04B2 -> 04B3 ->
XINT-002-06A -> ART-04C1 -> 04C2 -> XINT-002-05A. This ensures fixed-service pre-submit materialization is active
before contributor preparation can become live.

WS-XINT-002-04A activates only `artifact.guide_source.ingest`. The existing
permission belongs only to the Project Manager role and is evaluated through an
active covered grant: system-scoped or exact-project. Its prepared capability locks the
actor, exact identity link, and matched grant before byte intake; final
consumption binds the ART-locked project, draft guide, snapshot, item,
operation/request digests, and server-computed byte facts. `WS-XINT-002-04B`
separately activates guide-source read and binding creation for their exact
fixed service identities. Both use opaque transaction-bound PREP handles bound
to the complete verified-content and setup-generation facts; neither authority
is inherited from the Project Manager uploader.

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
ownership. AUTH-07A registered each row's stable `ActionId`, approved
`PermissionId`, historical owner value, and initial `planned` availability.
`WS-AUTH-001-ART-CUSTODY` has now replaced only those historical owner values
with the exact AUTH activation custodians below; mappings and ART
hidden-behavior ownership are unchanged, while reviewed activation chunks may
change availability. Its principal-class and
canonical-resource columns are not AUTH
registry fields and are not executable authority; the owning WS-ART chunk adopts
them with its hidden canonical resource composer, guards, surface declaration,
and behavior tests. The complete AUTH activation-custody transfer is separately
canonical in
`.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/AUTH_ART_HANDOFF.md`.
A mapping is not a permission alias.

| AUTH activation custodian | Exact ActionIds and current availability |
|---|---|
| `WS-AUTH-001-ART-02D-INTERNAL` | Active: `artifact.verification.execute`, `artifact.pending_work.scan`, `artifact.put_attempt.resolve` |
| `WS-AUTH-001-ART-02D-OPERATOR` | `artifact.binding.read`, `artifact.replica.read`, `artifact.receipt.read`, `artifact.verification_job.read`, `artifact.verification_job.retry`, `artifact.recovery_attempt.read`, `artifact.audit.read`, `operations.artifact_storage_admission.read` |
| `WS-XINT-002-04A` | Active: `artifact.guide_source.ingest` |
| `WS-XINT-002-04B` | Active: `artifact.guide_source.read`, `artifact.guide_source.binding.create` |
| `WS-XINT-002-05A` | `artifact.submission_bundle.prepare` |
| `WS-XINT-002-06A` | `artifact.pre_submit.checker_input.materialize` |
| `WS-XINT-002-05B` | `artifact.submission.binding.create` |
| `WS-XINT-002-06B` | `artifact.post_submit.checker_input.materialize`, `artifact.checker_output.write`, `artifact.checker_output.binding.create` |
| `WS-XINT-002-07A` | `artifact.review_packet.materialize` only |
| Future REV-owned activation, not approved for v0.1 | `artifact.review_evidence.binding.create` remains planned/unavailable |

The approved v0.1 review flow has a reviewer decision plus note/findings bound
to the reviewed Submission. It does not include a reviewer-uploaded artifact.
Therefore 07A activates packet materialization only; evidence binding remains
planned and unavailable unless a later REV-owned intent explicitly approves it.

The `OPERATOR` suffix names future activation custody only; it creates no
Operator grant or entitlement. WS-XINT-002-03 activates the three internal
service actions, WS-XINT-002-04A activates guide-source ingest, and
WS-XINT-002-04B activates the two fixed-service guide binding/read actions; the
other 16 ART actions remain planned and unavailable.
Migration `0037` admits the exact privacy-bounded ART resource-context digest
in append-only authorization decision facts; it adds no table or column.
`artifact.verification_job.retry` requires its own later evaluator, guards, and
independent activation proof; read/status proof cannot activate retry. The
historical ART transfer added no migration; WS-XINT-002-01 reconciles the
closed catalogue through migration `0036`. The separately started REV custody
transfer is also complete: all 19 REV rows now name exact AUTH custodians,
remain planned and unavailable, and add no migration.

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
| `artifact.guide_source.ingest` | `artifact.guide_source.ingest` | exact covered Project Manager | guide-source snapshot item | `03` |
| `artifact.guide_source.read` | `artifact.guide_source.read` | fixed guide-reader service | guide-source binding and verified replica | `03` |
| `artifact.submission_bundle.prepare` | `submission.create` | assigned contributor | exact task/admission context | `04C2` |
| `artifact.guide_source.binding.create` | `artifact.binding.create` | fixed binding service | guide-source snapshot item | `03` |
| `artifact.submission.binding.create` | `artifact.binding.create` | fixed binding service | submission | `05` |
| `artifact.checker_output.binding.create` | `artifact.binding.create` | fixed binding service | checker run | `06B` |
| `artifact.verification.execute` | `artifact.verification.execute` | fixed verifier service | verification job | `02D` |
| `artifact.pending_work.scan` | `artifact.pending_work.scan` | fixed scheduler service | system pending-work scope | `02D` |
| `artifact.put_attempt.resolve` | `artifact.put_attempt.resolve` | fixed put-resolver service | put attempt | `02D` |
| `artifact.pre_submit.checker_input.materialize` | `artifact.checker_input.materialize` | fixed materializer service | task plus current process-local prepared-bundle generation; no scratch path/handle is serialized | `04B2/04B3` |
| `artifact.post_submit.checker_input.materialize` | `artifact.checker_input.materialize` | fixed materializer service | checker run and immutable bindings | `06A` |
| `artifact.checker_output.write` | `artifact.checker_output.write` | fixed checker-output service | checker run | `06B` |
| `artifact.review_packet.materialize` | `artifact.review_packet.materialize` | fixed materializer service | exact active lease and Submission packet | `07A` |
| `artifact.review_evidence.binding.create` | `artifact.binding.create` | fixed binding service | future REV-owned evidence slot; no approved v0.1 activation | future |

The resource-owning chunk cells above identify ART hidden-behavior custody; they
are distinct from the AUTH activation-custodian table and runtime
`ActionOwner`. XINT activation waves do not create new catalogue owner values.

The fixed internal service identities and their complete action sets are also
closed:

| Service identity | Allowed actions |
|---|---|
| `workstream.artifact.verifier` | `artifact.verification.execute` |
| `workstream.artifact.put_resolver` | `artifact.put_attempt.resolve` |
| `workstream.artifact.scheduler` | `artifact.pending_work.scan` |
| `workstream.artifact.binding` | active/activatable v0.1: `artifact.guide_source.binding.create`, `artifact.submission.binding.create`, `artifact.checker_output.binding.create`; planned/unavailable future: `artifact.review_evidence.binding.create` |
| `workstream.artifact.guide_reader` | `artifact.guide_source.read` |
| `workstream.artifact.materializer` | `artifact.pre_submit.checker_input.materialize`, `artifact.post_submit.checker_input.materialize`, `artifact.review_packet.materialize` |
| `workstream.artifact.checker_output` | `artifact.checker_output.write` |
| `workstream.project.setup` | `project.guide_sufficiency.run`, `project.submission_artifact_policy.derive`, `project.post_submit_checker_policy.derive`, `project.setup_run.update` |
| `workstream.review.preference_expiry` | `review.preference_expiry.run` |
| `workstream.review.lease_expiry` | `review.lease_expiry.run` |
| `workstream.review.authority_invalidation_reconciliation` | `review.reconcile.run` |
| `workstream.review.reconciliation` | `review.reconcile.run` |
| `workstream.review.artifact_reference_reconciliation` | `review.artifact_reference.reconcile` |
| `workstream.review.projection` | `review.projection.rebuild` |

The hidden 04B2 prepared resource binds task, assignment, project, effective
submission-artifact-policy ID, pre-submit checker-policy ID, process-local
prepared generation, plan hash, catalogue-manifest hash, archive SHA-256/byte
count, and semantic-manifest hash. The fixed materializer consumes the opaque
prepared handle before any prepared-byte read, ZIP open, workspace reservation,
or checker fact. `AUTH_ART_04B` remains the catalogue owner; XINT-06A later
activates the action after hidden 04B3. ART does not activate it.

`workstream.project.setup` was the eighth fixed identity when AUTH-12B merged;
02C expands the current registry to fourteen identities. AUTH-12E activates only
`project.guide_sufficiency.run` for the exact internal setup-service command;
the other three project-setup actions and all six REV rows remain planned and
unavailable. Registration makes the
identity selectable by the existing controlled provisioning route but creates
no ActorProfile, ActorIdentityLink, role, grant, or executable authority by
itself; migration `0043_project_setup_service` only expands the closed database
identity constraint.

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
denied every fixed-service action outside its row. Human authorization remains
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
3. Build the closed request-scoped
   `HumanAuthorizationContext | ServiceAuthorizationContext` union without
   token-role authority. Only the service variant carries a required, closed
   `service_identity`.
4. Load the canonical resource through its owning repository/service.
5. Compose `ResourceContext` in the application service.
6. Load active candidate grants using database time.
7. Expand only registered permission candidates compatible with grant scope.
8. Apply actor, exact-project, ownership, assignment, separation-of-duties,
   task-ban, and lifecycle guards.
9. For actor-self reads/updates and sensitive mutations, revalidate current
   identity or authority inside the same transaction immediately before acting.
10. Return allow or a stable denial code without leaking hidden resources.

Authorization decisions are request-scoped and are not cached across requests.
Each decision carries a bounded SHA-256 digest of its complete typed resource
context so feature code cannot reuse it with substituted role, scope, target,
or replay facts. List filtering occurs before counts and pagination cursors.

Context-type dispatch occurs before candidate lookup. A service context never
enters actor-self, administrative-grant, project-grant, contributor, or human
rate-control paths. AUTH checks exact `ActionId` membership in the fixed
identity's static matrix row before checking availability; a different row
denies even when both actions share one `PermissionId`. An own-row action still
denies while its availability is `planned`.

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

The PREP foundation issues handles for `actor.profile.update_self`, the eight
active AdminRoleGrant-backed administrative mutations, the three active fixed
ART foundation service actions, Project Manager
`artifact.guide_source.ingest`, and the fixed-service
`artifact.guide_source.binding.create` and `artifact.guide_source.read`
actions. Submission, checker, review, and generic artifact-read actions remain
planned and issue no handle.
Actor-self preparation locks the exact caller
profile and then its exact identity link. Administrative preparation locks
`AuthorityControl(id=1)`, the exact request profile, exact request identity
link, and one deterministic effective AdminRoleGrant. The caller supplies an
independent expected ActionId when consuming the handle; AUTH checks it before
consumption, then checks the canonical request digest, idempotency UUID, exact
root transaction, and final actor-self/system/exact-project scope. A matching
attempt consumes the handle permanently before evaluation or evidence staging.
Cancellation and failures propagate to caller-owned rollback and never restore
the capability.

Preparation-time planned fixed-service denial has no final resource context, so
it returns the bounded `action_unavailable` outcome without staging evidence.
An exact-consume denial stages its decision only in the caller transaction; the
required rollback removes that event with participant state. PREP never
restages or commits denial evidence separately.

WS-XINT-002-02 closes the process-local PREP-to-ART operation interface without
activating an action. Durable ART mutation requests carry the opaque
`PreparedAuthorizationHandle`, never a raw `AuthorizationContext`; each typed
method fixes its expected action and accepts no caller-selected action or
generic facts map. The handle is non-Pydantic and cannot enter route schemas,
outbox/Celery payloads, provider interfaces, or serialized contracts. Exact
feature contexts and session/root-bound composer proofs remain owned by the
later evidence-backed activation chunks.

PREP's neutral PostgreSQL participant remains a test proof that final facts, one
decision event, participant work, and caller commit or rollback share the same
transaction. WS-XINT-002-03 adds the first active feature consumer: exact typed
prepared capabilities for the ART verifier, pending-work scanner, and
put-attempt resolver. Fixed services are locked and refreshed before either an
active-action decision or a still-planned `action_unavailable` denial;
still-planned actions issue no handle. For ART adapter calls only, any exact
denial is retained across the caller rollback and restaged through AUTH's
bounded public operation in a clean AUTH-only transaction. General PREP callers
do not restage rolled-back denial evidence. ProjectRoleGrant does not exist in
PREP; AUTH-10 must add its exact row lock, evaluator branch, and crossed-
revocation evidence before an exact-project product consumer can use that
authority source.

WS-XINT-002-04A adds the first active human feature consumer. Guide ingest
preparation locks the caller profile, exact identity link, and one active
covered Project Manager AdminRoleGrant before byte intake. ART then locks the
project, draft guide, snapshot, and item and supplies operation/request digests
plus server-computed digest, byte count, and media type for final consumption.
The allowed decision evidence carries the matched grant/project and exact final
resource-context digest in the same transaction as admission.

Service identity, static service-action matrix membership, and action
availability are immutable code-owned validations after the service profile and
link locks; they are not database rows or lock targets. Existing actor-self,
administrative, and lifecycle mutations must use the same authority-row order
before any prepared consumer ships.

AUTH-09E supplies the reusable transaction-local service-authority lock and
revalidation seam: reload and lock profile then exact link, recheck row
identity, lifecycle, immutable service identity, exact matrix membership, and
current action availability, and return refreshed typed authority without
committing. Later feature activation chunks own locked feature-row
recomposition, their exact `ResourceContext`, and terminal mutation proof.

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
Self-update through ordinary request authorization retains its existing
revalidation behavior; prepared self-update locks the exact profile followed by
its exact link,
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

Exact active resolution may stage monotonic profile/link observation timestamps
in the caller-owned request transaction. Admission denial stages no
observations. Planned-action denial, cancellation, decision-evidence failure,
or other request failure rolls staged observations back; bounded denial
evidence is restaged only from a clean transaction and contains no issuer,
subject, bearer material, claims, scopes, provider data, or service secret.

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
enter task-assignment reconciliation and persists `auth13_assignment`. Reviewer
revocation creates only the REV-owned review obligation and persists
`rev_reviewer_obligation`; adjudicator invalidation persists `none` and remains
dormant until its lifecycle is enabled. Revoking any one project role leaves the
other roles and all AdminRoleGrants unchanged. Consumers verify the cause event,
grant ID, actor, project, role, and closed future-obligation token before
changing product state.

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
POST /api/v1/actor-identity-links/{identity_link_id}/revoke|reactivate
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
effective system Access Administrators only. AUTH-09D-B activates exact
identity-link revoke and reactivate for the same authority. AUTH-10B activates
the concealed project-role reads, and AUTH-10C activates exact-role issue and
revoke mutations for covered Project Managers. Those mutations use
`Idempotency-Key`, transaction-bound PREP, immutable qualification snapshots,
canonical replay validation, and one route-owned commit. Issue requires a
different active human with an active identity link; revoke remains available
after target suspension or identity-link revocation so authority cannot become
irremovable. AUTH-11B activates `GET /api/v1/projects/{project_id}` and
project-scoped `GET /api/v1/actors/me/authorization-context?project_id=...`.
Both resolve the canonical project and use current local grants only. Project
identity returns the registered full identity projection to effective Operator,
Project Manager, Finance Authority, or Audit Authority grants, and only id,
name, and status to exact-project Submitter, Reviewer, or Adjudicator grants.
The self context lists effective role names and active route-backed project
actions; it exposes no grant ids, identity-link data, planned actions, or
unrelated system authority.

AUTH-11C1 activates the six setup-run, sufficiency-report, draft submission
artifact policy, and post-submit checker setup GET actions. Each route resolves
and locks the canonical project, guide/version, exact child or collection, and
source-snapshot facts before requiring a covered Project Manager, scoped Audit
Authority, or system Operator grant. Missing, cross-project, cross-guide,
revoked, and stale bindings share the concealed project-read response.
Issuer-provided role metadata is excluded from product decisions; contributor grants do not
cover these diagnostics, and these read permissions provide no mutation
authority.

| AUTH-11C1 public GET route | ActionId | PermissionId |
|---|---|---|
| `/api/v1/projects/{project_id}/guides/{guide_id}/setup-runs/latest` | `project.setup_run.read` | `project.setup_diagnostic.read` |
| `/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports` | `project.guide_sufficiency_report.list` | `project.setup_diagnostic.read` |
| `/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}` | `project.guide_sufficiency_report.read` | `project.setup_diagnostic.read` |
| `/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies` | `project.submission_artifact_policy.list` | `project.effective_policy.read` |
| `/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}` | `project.submission_artifact_policy.read` | `project.effective_policy.read` |
| `/api/v1/projects/{project_id}/guides/{guide_id}/post-submit-checker-policy/setup` | `project.post_submit_checker_policy_setup.read` | `project.effective_policy.read` |

AUTH-11C2 hard-cuts three current active-guide reads to local administrative
authority. Covered Project Manager and Audit Authority grants and system
Operator grants may read them. Finance Authority, Access Administrator,
project-role contributors, and services deny with the same concealed response
as a missing or stale resource.

| AUTH-11C2 public GET route | ActionId | PermissionId |
|---|---|---|
| `/api/v1/projects/{project_id}/guides/{guide_id}/effective-submission-artifact-policy` | `project.effective_submission_artifact_policy.read` | `project.effective_policy.read` |
| `/api/v1/projects/{project_id}/guides/{guide_id}/pre-submit-checker-policy` | `project.pre_submit_checker_policy.read` | `project.effective_policy.read` |
| `/api/v1/projects/{project_id}/active-guide` | `project.active_guide.read` | `project.read` |

The guide-bound policy routes expose only the approved/compiled chain for the
current active guide and latest canonical snapshot. The strict active-guide
response contains guide, source snapshot, sufficiency, submission artifact,
effective, pre-submit checker, post-submit checker, review, and revision
context. It excludes retired compensation configuration. Every returned row
and source item is locked and hash-revalidated through projection and commit.
Draft, superseded, replaced, incomplete, ambiguous, corrupt, or stale bindings
conceal. Contributor guide requirements remain on task work-context and
submission-requirements surfaces.

AUTH-12A registered the complete project-mutation vocabulary below as planned
and unavailable. AUTH-12C activates `project.create`, and AUTH-12D activates
the three draft guide/source-metadata actions identified below; every remaining
row stays planned. A planned action fails with `action_unavailable` before a
prepared handle or allowed decision evidence can exist. `project.create` alone
derives system scope; every other action derives the exact project from its
typed resource.

`POST /api/v1/projects` requires an active human, the exact active identity
link, an effective system-scoped Project Manager grant, and a UUID
`Idempotency-Key`. Project-owned replay state supplies stable server operation
and project identities before PREP. Final consumption binds those identities,
the validated body digest, actor, link, grant, generation, request transaction,
and action. The project shell, authorization event, provenance, and committed
replay result persist atomically. Verified-token role observations,
project-scoped grants, service
actors, copied handles, changed replay input, revoked authority, and stale or
wrong transactions do not authorize creation. This action creates no guide,
setup run, task, submission, checker, review, contribution, compensation,
reputation, policy, or activation state.

An exact committed retry is response recovery, not another creation attempt.
It validates the same actor/action/key/request digest and the database-enforced
committed custody chain, then returns the original response without new PREP or
allowed evidence. Later grant revocation denies new or changed creation
requests but does not rewrite an already committed idempotent response.

Guide create, guide update, and source-snapshot metadata create require an
active human with an effective system-scoped or exact-project Project Manager
grant carrying `project.guide.manage`. Each route requires a UUID
`Idempotency-Key` before actor first-access provisioning and consumes one opaque,
transaction-bound PREP handle after locking the exact project, draft guide, and
current source lineage. Guide create produces only a draft guide. Snapshot
creation separately records the sanitized source manifest and may commit one
setup-run queue intent; broker dispatch happens only after commit and never
carries the prepared handle.

Guide create/update no longer accept embedded review, revision, retired
payout/economic, or contribution-record configuration fields. Guide source markdown
may change before the first source snapshot, becomes immutable after capture,
and bounded metadata such as `change_summary` remains editable while the guide
is draft. Exact committed retries return the recorded response without another
mutation, setup run, or dispatch. Changed, concurrent-pending, cross-project,
stale-lineage, revoked, wrong-action, wrong-resource, or wrong-transaction use
fails closed with no product write.

Review and revision policy configuration uses two separate guide-bound `PUT`
routes. Each requires an exact covered-project Project Manager grant, a UUID
`Idempotency-Key`, and an HTTP `If-Match` precondition: a quoted opaque selector
binding the current policy ID, generation, and digest for replacement or the
exact `"no-current-policy"` sentinel for initial
attachment. The server normalizes the complete policy semantics, computes the
canonical digest, consumes one transaction-bound PREP handle after locking the
draft guide and predecessor, appends an immutable version with authorization
provenance, and advances only that policy selector. Draft guides may attach the
two policies in either order; activation still requires both. Active guide
policy selection remains frozen.

Guide sufficiency has three active mutation actions. Public requests require a
covered Project Manager, canonical human actor/link resolution, and UUID
idempotency. PREP binds the draft guide/version, latest source snapshot/hash,
setup generation, report when applicable, operation/request digest, and final
material/stale-output facts. Agent execution occurs after cheap preflight and
outside any prepared handle; persistence obtains fresh authority. The fixed
`workstream.project.setup` service may resolve only the run action internally
with exact setup custody and no matched human grant.

| ActionId | PermissionId | Activation owner |
|---|---|---|
| `project.create` (active) | `project.create` | `WS-AUTH-001-12C` |
| `project.guide.create` (active) | `project.guide.manage` | `WS-AUTH-001-12D` |
| `project.guide.update` (active) | `project.guide.manage` | `WS-AUTH-001-12D` |
| `project.guide_source_snapshot.create` (active) | `project.guide.manage` | `WS-AUTH-001-12D` |
| `project.review_policy.update` (active) | `project.review_policy.manage` | `WS-XINT-003-02B` |
| `project.revision_policy.update` (active) | `project.review_policy.manage` | `WS-XINT-003-02B` |
| `project.guide_sufficiency_report.create` (active) | `project.guide.manage` | `WS-AUTH-001-12E` |
| `project.guide_sufficiency.run` (active) | `project.guide.manage` | `WS-AUTH-001-12E` |
| `project.guide_sufficiency.warnings.acknowledge` (active) | `project.guide.manage` | `WS-AUTH-001-12E` |
| `project.submission_artifact_policy.create` | `project.effective_policy.manage` | `WS-AUTH-001-12F2` |
| `project.submission_artifact_policy.derive` | `project.effective_policy.manage` | `WS-AUTH-001-12F3` |
| `project.submission_artifact_policy.update` | `project.effective_policy.manage` | `WS-AUTH-001-12F2` |
| `project.submission_artifact_policy.approve` | `project.effective_policy.manage` | `WS-AUTH-001-12F4` |
| `project.post_submit_checker_policy.approve` | `project.effective_policy.manage` | `WS-AUTH-001-12G` |
| `project.post_submit_checker_policy.correction.request` | `project.effective_policy.manage` | `WS-AUTH-001-12G` |
| `project.post_submit_checker_policy.derive` | `project.effective_policy.manage` | `WS-AUTH-001-12G` |
| `project.setup_run.update` | `project.guide.manage` | `WS-AUTH-001-12B2` |
| `project.guide.activate` | `project.guide.manage` | `WS-AUTH-001-12H` |

Migration `0054_guide_sufficiency_authority` preserves historical sufficiency
rows as readable, unattributed records while requiring complete creation or
acknowledgement authority provenance for new 12E mutations. Its replay ledger
is append-only, and downgrade is refused after any 12E replay or provenance
exists. Operators must not delete authority or product evidence to force a
rollback.

`WS-AUTH-001-12F` is a planning-only parent and activates nothing. 12F1 owns
the zero-activation PREP/replay/provenance foundation; 12F2 owns explicitly
manual Project Manager drafts; 12F3 owns automatic fixed
`workstream.project.setup` derivation and removes public inline derivation; and
12F4 owns Project Manager approval plus the atomic effective/pre-submit chain.
12G and the final setup-service cutover depend on merged 12F4.

The 12F1 foundation binds each future submission-policy handle to the exact
project/guide/source lineage, mutation target, operation and request digests,
policy generation, actor/link and grant-or-fixed-service custody, and current
root transaction. Approval also binds the immutable default-catalogue manifest,
ordered and disabled entry configuration digests, compiler/bundle schema, and
compiled/effective output hashes. Its replay reservation distinguishes human
idempotency from fixed setup-service task custody and permits only
`pending -> committed`; it does not perform a product mutation or own commit.
Migration `0057_submission_policy_authority` preserves existing product rows in
the all-null unattributed shape until the 12F2-12F4 route cutovers. Any replay
row—including pending—or attributed provenance blocks downgrade. None of this
makes the four catalogue actions executable. Any submission-policy
authorization audit event, including denied evidence, also blocks downgrade so
the admitted evidence vocabulary is never removed while referenced.

Migration `0041_project_mutation_evidence` extends only the closed audit
action-to-permission evidence constraint. It follows ART migration
`0040_guide_materialization`, adds no permission, and refuses downgrade after
direct or idempotency-linked evidence uses any new action.

The two collection routes return and transactionally bind at most the newest
100 canonical rows in deterministic newest-first order. Older retained records
remain available only through their exact individually authorized read route.

`WS-AUTH-001-CONTRIBUTOR-FOUNDATION` adds no permission or authorization path.
It clean-cuts TaskAssignment and Submission attribution to `contributor_id`,
binds both fields to canonical human ActorProfiles in PostgreSQL, and exposes
one actor-owned transaction participant for claim and submission. The
participant locks the exact profile and verified issuer/subject link, requires
both to be active human identity state, returns no identity or authority data,
and runs after coarse legacy role admission but before resource locks. A
non-human or inactive identity returns `active_contributor_required`; missing,
mismatched, or unavailable canonical identity state returns retryable
`contributor_identity_unavailable`.

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
14. `WS-AUTH-001-CONTRIBUTOR-FOUNDATION`: canonical-human TaskAssignment and
    Submission attribution plus transaction-local active identity
    revalidation;
15. `WS-AUTH-001-09E`: fixed service runtime admission without human grant
    evaluation or feature action activation;
16. `WS-AUTH-001-ART-CUSTODY` and `WS-AUTH-001-REV-CUSTODY`:
    availability-neutral transfer to exact AUTH activation owners;
17. `WS-AUTH-001-PREP`: prepared mutation authorization protocol;
18. `WS-AUTH-001-10`: independent project contributor grants, with 10B1
    establishing durable authorization-read rate control before 10B2 exposes
    candidate and grant-history reads;
19. `WS-AUTH-001-11` through `WS-AUTH-001-14`: complete resource-family
    cutovers;
20. `WS-AUTH-001-15`: obsolete authority removal and scanner enforcement;
21. `WS-AUTH-001-16`: conformance, observability, concurrency, and live API
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
Migration `0033_authorization_read_rate` extends that same durable
counter with the closed `authorization_read` scope. Its dependency remains
unattached and activates no action until AUTH-10B2. The dedicated default is
120 requests per 60 seconds per verified issuer/subject digest, independently
configurable within the existing bounded limit and window ranges.

AUTH-10B2 activates only `project.contributor_candidate.list`,
`project_role_grant.list`, and `project_role_grant.read`. Their canonical targets
are the server-loaded project and, for detail, the grant joined through that
project. Candidate discovery is Project-Manager-only and permits draft, active,
and paused projects; grant history permits covered Project Manager or Audit
Authority access in every project state. Services and unsupported agent/Space
subjects are concealed before project lookup. Authorization denials, missing
resources, project/grant mismatch, and candidate lifecycle denial use one public
404 shape while bounded kernel denials retain their established audit evidence.

Candidate pages expose exactly actor profile ID plus nullable display name.
Grant pages accept only optional active/revoked status and
submitter/reviewer/adjudicator role filters, a 1..100 limit (default 50), and a
cursor bounded to 512 characters. Each grant exposes exactly `id`, `project_id`,
`actor_profile_id`, `role`, `status`, `version`, `grant_method`,
`qualification_snapshot`, both granting actor/admin-grant identifiers,
`granted_at`, `grant_reason`, and the three present-but-nullable revocation
fields. The nested snapshot exposes exactly its ID, requested role, bounded
skills and reputation availability/reference objects, prior-project and
external-expertise references, both capturing actor/admin-grant identifiers,
and capture time. Both page
envelopes are exactly `items` and `next_cursor`, without totals. A strict signed
keyset cursor binds action, project, normalized filters, limit, ordering,
timestamp, and UUID. The required independent 32-byte Base64 cursor HMAC key
fails startup when absent or invalid; coordinated rotation invalidates all
outstanding cursors. AUTH-10B2 adds no migration and does not change PREP or
grant mutation behavior.

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
