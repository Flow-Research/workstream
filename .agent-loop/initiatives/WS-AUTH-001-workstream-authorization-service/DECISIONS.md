# Decisions: WS-AUTH-001 - Workstream Authorization Service

## D1: Adopt WS-AUTH-001 as the authorization authority source

Status: accepted by the user on 2026-07-11.

`WS-AUTH-001` supersedes the repository's token-role bootstrap and current
multi-profile authorization semantics. Existing code and docs remain evidence
of current behavior, not the target authority contract.

## D2: Preserve `/api/v1`

Status: accepted by the user on 2026-07-11.

The repository's existing `/api/v1` namespace remains canonical. The imported
specification's `/v1` examples will be reconciled during the baseline-adoption
chunk. Workstream will not expose two versioned route trees as permanent
aliases.

## D3: Prioritize authorization foundation

Status: accepted by the user on 2026-07-11.

Authorization remains the priority before later locked runtime hardening. The
user separately directed and merged `WS-POL-002-03` through PR #90 as
`a7aa474`; that completed approval API does not activate `WS-POL-002-04` or
change the authorization priority.

## L0 human approval boundary

The user explicitly approved the authorization direction, source precedence,
API namespace, and priority recorded in D1-D3 on 2026-07-11. On 2026-07-11,
after the planning and post-merge memory PRs merged, the user said "ok start" in
direct response to the recorded D4-D10 approval and separate chunk-start gate.
That response approves D4-D10 and starts only `WS-AUTH-001-01`. Every bounded
implementation chunk remains L1 and retains its own human PR/merge checkpoint.

## D4: No dual canonical authority

Status: accepted by the user on 2026-07-11.

Token roles may be retained as non-authoritative diagnostic input during a
bounded migration only. A protected command must never accept either a token
role or a local permission as interchangeable proof. Cutover chunks replace
authorization for complete resource surfaces and remove the old check.

## D5: Preserve historical actor identifiers where classification is safe

Status: accepted by the user on 2026-07-11.

Existing `ActorIdentity.actor_id` values for externally verified callers are
UUID5 strings and are referenced throughout tasks, submissions, checker runs,
project provenance, and audit rows. For a classified legacy row, that UUID
becomes the canonical `ActorProfile.id`; the new `ActorIdentityLink` receives a
separate UUID. Migration must validate UUID shape and uniqueness before reuse.
Invalid or ambiguous rows fail preflight and are not silently rewritten.

The unrelated UUIDs on legacy typed `actor_profiles` rows are workflow-row IDs,
not actor IDs, and never become canonical profile IDs.

## D6: Existing typed profiles do not become grants

Status: accepted by the user on 2026-07-11.

Observed or active `worker`, `reviewer`, `admin`, or `project_manager` profile
rows do not create `AdminRoleGrant` or `ProjectRoleGrant` records. Skills and
non-authoritative workflow metadata may be preserved under a clearly named
metadata model only when required by an existing workflow.

## D7: Internal workers use explicit system authority

Status: system-authority requirement retained; ActorProfile clause superseded by
D20 and D22.

Project setup, pre-review gating, reconciliation, and repair work use fixed
Workstream service ActorProfiles and registered system permissions. They do not
receive fabricated human admin or project contributor roles.

## D8: Production issuer details remain configuration

Status: accepted by the user on 2026-07-11.

The token adapter will require explicit issuer, audience, JWKS URL, algorithm,
scope, clock-skew, and cache configuration and will fail closed when incomplete.
The real issuer values are required for live production-token proof, not for
deterministic adapter implementation with local JWKS fixtures.

## D9: Authority evidence is foundational

Status: accepted by the user on 2026-07-11 after internal review repair.

Request/correlation context, canonical idempotency records, and the shared
append-only authority-event writer are introduced before canonical actor
persistence and before any authority-changing public API. Every later authority
mutation commits state, idempotency result, audit event, and invalidation event
atomically. The final evidence chunk verifies completeness; it does not invent
or backfill the evidence model.

## D10: Legacy classification uses a versioned supported manifest

Status: accepted by the user on 2026-07-11 after internal review repair.

Non-empty legacy registries require a versioned JSON classification manifest
processed by a supported management/preflight tool. Entries bind exact legacy
actor ID, canonical issuer, opaque subject, and `subject_kind`. The tool rejects
duplicates, stale/missing rows, mismatches, unknown fields, and unsupported
kinds; supports dry-run; emits a checksum-bound report; and never writes grants.
The schema migration consumes only validated staged classification evidence or
fails closed. Manual SQL is not a supported path.

## D11: Contributor is the human product term

Status: umbrella terminology retained; combined-role clause superseded by D21.

Contributor is the umbrella term for a human participating in Workstream.
D11 originally coupled project contribution capabilities through a combined
grant option. D21 supersedes only that role-shape clause with three independent
exact-project grants. Celery, checker, setup, and reconciliation workers are
internal services and background jobs, not human product roles. Existing
human-role values using the old term are migration inputs to remove, not target
product vocabulary or authority concepts.

The field cutover is explicitly owned as follows:

- `WS-AUTH-001-CONTRIBUTOR-FOUNDATION` clean-cuts both retired assignment and
  Submission human-owner identifiers to `contributor_id` across
  storage, models, services, schemas, audits, and tests. It also supplies
  database-backed canonical-human ActorProfile lineage and a transaction-local
  active-human revalidation capability.
- `WS-AUTH-001-13` consumes the canonical assignment field during task
  authorization cutover; it does not rename it again.
- `WS-AUTH-001-14` consumes the canonical Submission owner field and renames
  the remaining submission attestation and checker-result visibility fields
  from legacy `worker_*` names to their `contributor_*` equivalents. It also
  renames the submission-policy JSON field `worker_facing_fix` to
  `contributor_facing_fix` across derivation schemas, prompts, persistence, and
  tests.
- Revision replay is not implemented yet and must begin with
  `contributor_claim_status`; it must not introduce the legacy name.
- `ContributionRecord`, `CompensationAward`,
  `CompensationFulfillmentReceipt`, and `CompensationStatusProjection` are
  owned by WS-CON and must use `contributor_id` where contributor attribution
  applies; no new legacy column is permitted.

Each owning migration preserves values and immutable attribution, uses only a
bounded transitional storage compatibility layer inside the migration chunk,
exposes no legacy public API alias, and removes the old column/name before that
chunk completes.

## D12: Verified-token production dependencies

Status: accepted by the user on 2026-07-11.

`WS-AUTH-001-02` proposes two exact base dependency changes:

- add `PyJWT[crypto]>=2.13,<3.0` for maintained JOSE/JWK parsing and asymmetric
  signature verification; and
- move the existing `httpx>=0.27,<1.0` requirement from the development extra
  to base dependencies for separately controlled async JWKS and introspection
  clients.

PyJWT's network JWKS client will not be used because Workstream owns redirect,
timeout, streaming-size, cache, and transport-injection policy. The standard
library has no safe equivalent for asymmetric JOSE verification, and
hand-written JOSE or HTTP cryptography is outside the approved design. Chunk
start does not imply dependency approval. No production dependency or runtime
implementation may change until the user explicitly accepts D12 and that
acceptance is recorded here. The user explicitly approved D12 by replying
"ok apporeved" after the final preimplementation plan review passed.

## D13: Identity issuer is the stable verification boundary

Status: accepted by the user on 2026-07-13.

Workstream depends on one provider-neutral `IdentityIssuerVerifier` capability
port. It extends the repository-wide `ExternalServiceAdapter` convention and
is constructed through the typed
`ExternalServiceAdapterFactory[IdentityIssuerVerifier]` foundation being
prepared by `WS-ART-001-02A1`. AUTH must adopt that merged shared foundation; it
must not create a second generic adapter registry or factory.

The `/auth` dependency and product authorization layers must not change when an
additional external identity issuer is configured. Issuer-specific discovery,
JWKS, signature, claim, and introspection behavior remains behind explicit
adapter registration, construction, and configuration; it does not become a
second internal auth system or grant Workstream product authority.

The current `AuthVerifier` port, `FlowAuthVerifier` adapter, and `flow_auth_*`
configuration names are migration inputs rather than the target vocabulary.
Their rename must be one bounded, atomic specification and implementation
chunk covering the port, adapter, factory, configuration compatibility,
tests, operator documentation, and stale-name proof. AUTH-04A does not absorb
that cross-cutting rename because its reviewed request/error scope is already
at the production size circuit breaker. The owning follow-up chunk is blocked
until the shared convention merges, and must then remove the old AUTH factory
entry point and migrate all callers in one clean cut. It must be planned and
reviewed before implementation; no compatibility factory alias, duplicate
verifier, service locator, or public login/session API may be introduced.

## D14: Artifact operations use centralized authorization

Status: accepted by the user on 2026-07-14.

The artifact subsystem owns upload/storage, retention, replication, integrity,
and reconciliation mechanics behind the shared object-storage adapter
foundation. It does not own or infer product authority. Every human-initiated
or internal-service artifact operation must be authorized by Workstream's one
central authorization kernel using an operation-specific permission and the
exact project/resource scope before an adapter performs external I/O.

Human callers resolve through canonical `ActorProfile`, identity-link status,
and the applicable administrative or exact-project contributor grant. Artifact
storage, retention, and reconciliation services authenticate as explicitly
provisioned service principals with registered system permissions; they are not
Contributors and never receive fabricated human roles. Upload, read, retain,
release/delete, replicate, verify, and reconcile authority are distinct and do
not imply one another.

The authorization decision and operation receipt must share bounded request/
correlation evidence, resource identity, operation, and service principal.
Receipts prove that storage work occurred; they do not create authority. AUTH-07A
registers exact artifact permissions and planned actions, AUTH-07B introduces
the central kernel, AUTH-08 defines applicable Operator grants, AUTH-09A owns
the static service-action matrix, AUTH-09B provisions fixed service
ActorProfiles and ActorIdentityLinks, and AUTH-09E admits them at runtime. Each
owning WS-ART feature chunk supplies hidden canonical resource composition,
guards, surface declarations, decision calls, behavior, and tests.
Dedicated AUTH activation custodians then integrate exact evaluators and alone
change availability. AUTH-12, AUTH-14, and AUTH-15 are not alternate artifact
activation paths. AUTH-04B adds no artifact permission or route attachment.

## D15: Adopt a staged typed action and resource catalogue

Status: accepted by the user on 2026-07-14 after repository mapping and internal
design review.

AUTH-07A introduces a closed typed action registry, and AUTH-07B activates the
first bounded actions. Each active `ActionId` binds
one already approved `PermissionId` to one canonical authorization target,
candidate authority sources, mandatory guards, principal class, and
transaction-revalidation rule. Multiple closed actions may map to one retained
broad permission while using distinct targets and guards; routes cannot supply
arbitrary permission/target pairs. Creates authorize against an existing parent
or `system` target. Feature
repositories remain persistence owners; feature application services or
feature-owned loaders compose closed, typed per-resource `ResourceContext`
variants and register at the composition root without making AUTH a second
domain-query layer. Guard definitions declare their required resource facts;
unknown, missing, extra, or mistyped facts fail closed.

Each protected route or asynchronous command declares one primary registered
action as its authorization entry point. Domain invariants remain owned by the
feature service. Human bearer tokens are never executable worker authority,
and collection filtering occurs before counts or cursors. Catalogue adoption is
staged: AUTH-07A owns identifiers and planned metadata, AUTH-07B owns the first
self-route definitions, every later route-owning chunk through AUTH-15 owns
declarations during its feature cutover, and
AUTH-16 owns the aggregate generated route/command completeness manifest and
final no-bypass proof.

Reserved planned runtime metadata contains only stable `ActionId`, approved
`PermissionId`, exact AUTH activation custodian, and availability. It cannot
authorize and does not make AUTH the owner of foreign-domain facts or behavior.
Before a new planned action is registered, however, its owning feature must
publish a jointly approved typed contract naming principal class, canonical
resource type and facts, guards, surface, transaction owner, revalidation, and
hidden-behavior dependency. Registration records the four-field runtime row and
typed/PostgreSQL evidence mapping; activation later integrates the evaluator
only after hidden behavior merges. A feature chunk never changes availability.

`ActionId` is security-significant evidence. AUTH-07A adds typed/PostgreSQL
audit parity; AUTH-07B adds it to `AuthorizationDecision`, bounded logs/metrics,
and allowed/denied authority events. Historical events may remain null; every
AUTH-07B-or-later action-based decision event requires a registered identifier.
Planned IDs can be registered before activation because they encode
only identifier, approved permission, owner, and availability, not foreign
resource design.

The reviewed proposal did not receive independent normative precedence. Its
`/v1` prefix, broad-permission replacement, compatibility deletion, and invented
artifact, review, contribution, and compensation resources were rejected. The
adopted `/api/v1` namespace and original 52 approved permission identifiers
were unchanged by that catalogue review. The later approved artifact-storage
contract added 21 exact identifiers, making the pre-D17 closed total 73.
AUTH-05A currently enforces a 49-identifier typed/PostgreSQL audit base; the
three already approved Operator recovery identifiers and 21 artifact
identifiers remain planned and non-executable until AUTH-07A adds typed/SQL audit
parity, the owning feature merges hidden behavior, and the dedicated AUTH
custodian activates each action. Other permission additions or renames still
require an approved specification/ADR change, typed and PostgreSQL registry
migration, audit-history treatment, cutover ownership, and rollback proof.
WS-REV, WS-CON, and the artifact-storage specification continue to own their
resources and state transitions.

At D15 acceptance, migration custody was recorded as follows: AUTH-05A owned
`0018`, AUTH-05B solely owned `0019`, AUTH-06 used `0020`, AUTH-07A action
evidence used `0021`, AUTH-08 used `0022`, and the AUTH-09A fixed-service
identity foundation used `0023`. AUTH-09B used `0024` for service-link
verification timestamps. AUTH-10 used `0025`, AUTH-11 used `0026`, AUTH-12 used
`0027`, AUTH-13 used `0028`, AUTH-14 used `0029`, and AUTH-15 used `0030`
so every new protected surface receives typed/PostgreSQL ActionId evidence
parity in its owning cutover. Feature-gated REV/ART additive registrations use
the next trusted-main migration head when their complete contracts become
executable; they do not reserve a number while blocked.

D29 supersedes only D15's future AUTH-10 through AUTH-15 migration allocation.
The merged historical ownership through AUTH-09B `0024` remains unchanged.

## D16: Split AUTH-07 at the catalogue and executable-kernel boundary

Status: accepted as a required L1 preimplementation repair on 2026-07-15.

Required architecture, security/auth, and QA/CI plan review found that the
combined AUTH-07 contract placed grant-backed administrative APIs before
AUTH-08, project capability composition before AUTH-10, and mixed the audit
migration with executable kernel/API behavior. No runtime code had started.

At the split boundary, AUTH-07A owned only the exact 73-PermissionId catalogue,
30 four-field
planned ActionId definitions, including both later self actions, and
action-aware audit migration `0021`. AUTH-07B
later owns the minimal deny-by-default kernel and activates only
`actor.profile.read_self` and `actor.profile.update_self`. Permission and
admin-role definition APIs move to AUTH-08; project-scoped authorization
context moves to AUTH-10. Each child retains its own merge and explicit-start
gate.

## D17: Adopt canonical review actions without moving review behavior into AUTH

Status: accepted by the user on 2026-07-15 after mapping the revised WS-REV
source against the implemented AUTH and ART contracts and completing internal
architecture, docs/security, and test/migration review.

AUTH-07A expands the closed catalogue to exactly 74 PermissionIds and 50
planned ActionIds. `review.queue.override` is the only additive PermissionId and
is explicitly the 25th post-`0020` permission; the historical 49-value set does
not change. Twenty planned actions were added: canonical `submission.create`
under `WS-AUTH-001-14`, plus 19 review actions initially labelled with exact
`WS-REV-001-05`, `06`, `07`, `08`, `09A`, `11`, and `12` feature chunks. All
additions remain four-field planned metadata and cannot authorize. D25
supersedes those feature labels as activation custody: REV still supplies
resource composition, guards, candidates, surface declarations, revalidation,
and behavior tests, while exact AUTH chunks own evaluator integration and
availability.

Initial and revision submissions share the same `submission.create` action,
permission, and route. There is no `submission.revise`, `review.assign`,
`review_revision.record`, or separately callable revision-preparation action.
Revision preparation is an internal participant and lifecycle guard of the
canonical submission command. Finding and finding-response evidence intake use
distinct actions mapped to existing `review.decision` and `submission.create`
permissions because each is a protected human command that can create artifact
state before the final transaction.

`artifact_recovery.request` is rejected. Operator recovery consumes the already
registered `artifact.verification_job.retry` action through the ART-owned
`ArtifactOperatorRecoveryPort`; ART retains recovery-attempt, execution,
fencing, and idempotency ownership. REV owns no projection dispatch/retry action
because the shared outbox owns dispatch, attempts, retry, dead-letter, and
delivery state. Immediate grant-revocation recovery remains a participant of
the originating AUTH mutation, while missed recovery uses the planned
`review.reconcile.run` action.

AUTH-07B must expose one stable public feature boundary: a request-scoped
`AuthorizationService` bound to the current `AuthorizationContext` and
caller-owned `AsyncSession`. Feature modules call
`require(action_id, typed_resource_context)`; the bound session is the only
transaction source. The service returns and stages one bounded decision, never
commits, and never accepts a raw
PermissionId, candidate grant, or guard. REV owns its ResourceContext composers
and lifecycle invariants and may import only that public AUTH interface and
closed types, never AUTH persistence or grant queries.

## D18: Administrative actions and grants activate together in AUTH-08

Status: accepted as the required L1 contract repair after AUTH-08's explicit
start on 2026-07-15.

AUTH-08 adds no PermissionId. It adds exactly seven ActionIds owned by AUTH-08:
`authorization.permission_catalogue.read`,
`authorization.admin_role_definitions.read`, `admin_role_grant.list`,
`actor.admin_role_grant_history.read`, `admin_role_grant.issue`,
`admin_role_grant.revoke`, and `admin_role_grant.bootstrap`. They map to the
existing `admin_role.read`, `admin_role.grant`, or `admin_role.revoke`
permissions. This preserves D15's one canonical target, candidate, guard set,
and principal type per action instead of collapsing definition reads, scoped
history reads, human mutations, and the local trust root. They activate only
with the one-time local bootstrap, exact five-role permission matrix, immutable
AdminRoleGrant persistence, grant-backed central-kernel evaluation, scoped
definition/history APIs, audit/idempotency parity, and final-administrator
locking in the same reviewed chunk. The merged 50-action catalogue therefore
becomes 57 actions with exactly nine active actions after AUTH-08; every other
action remains planned.

The local bootstrap command declares `admin_role_grant.bootstrap` in its command
manifest but does not fabricate a bearer AuthorizationContext or human grant.
HTTP surfaces continue to use only request-scoped
`AuthorizationService.require(action_id, typed_resource_context)`. System scope
is not superuser authority, token roles never become candidates, and AUTH-09
remains the owner of actor/link lifecycle mutations that must later reuse the
AuthorityControl-first final-administrator lock order.

For the two admin-grant mutations, this decision supersedes AUTH-05B's generic
grant-resource `effective=true -> false` invalidation placeholder. Issue
invalidates the target actor authority projection `false -> true`; revoke
invalidates it `true -> false`. AUTH-08 must update typed and PostgreSQL audit
validation together and prove both directions. Human-readable bounded grant and
revocation reasons live on immutable AdminRoleGrant history; request digests
remain in idempotency evidence, and audit reasons remain closed classifications.

## D19: Protected routes own commit and successful verification timestamps

Status: accepted after read-only AUTH-07B consumer review on 2026-07-15.

The reusable authorization dependency never commits an arbitrary open feature
transaction during successful teardown. Every protected route explicitly owns
the commit of its read/mutation plus authorization evidence, while dependency
teardown rolls back unfinished work. Authorization-evidence SQL failures map at
that composition boundary through a typed `AuthorizationEvidenceUnavailable`
to the existing retryable 503 `service_unavailable` envelope without partial
evidence or business state. Feature SQL errors remain route-owned. Route commit
failures use the same public retryable envelope but are not mislabeled as audit
failures, and rollback every staged participant before retry.

For an existing human actor, a successful protected request advances canonical
`ActorProfile.last_seen_at` and `ActorIdentityLink.last_verified_at` after
authorization in that route-owned transaction. D28 supersedes this decision's
original lock-order clause: every current helper locks profile then exact link
and uses `GREATEST(current_value, clock_timestamp())` so crossed commits cannot
regress recency. Authorization denial or persistence failure rolls the staged
timestamp changes back. This restores verification recency without letting
denied requests manufacture successful-use evidence. Service subjects remain
pre-resolution denials until AUTH-09E and cannot manufacture either timestamp.

## D20: Service ActorProfile is the fixed local service principal

Status: accepted by the user on 2026-07-16.

A service `ActorProfile` is Workstream's stable local service principal. It
carries one immutable, unique, closed `service_identity`; its
`ActorIdentityLink` contains the configured issuer and opaque service subject.
It receives no Contributor domain, AdminRoleGrant, or ProjectRoleGrant. Exact
service actions come only from one reviewed static matrix, never token claims,
display data, or database-authored grants.

## D21: Project contributor roles are independently granted

Status: accepted by the user on 2026-07-16 and supersedes D11's combined-role
clause.

The v0.1 ProjectRoleGrant values are exactly `submitter`, `reviewer`, and
`adjudicator`. A human may hold all three capabilities through independent
immutable rows. Each role is independently issued, revoked, regranted,
invalidated, and revalidated. There is no `both`, cross-role replacement,
replacement event, replacement reason, or replacement/supersession field.

Qualification evidence is bound by composite constraints to the same actor,
project, and exact requested role. One partial unique constraint permits only
one active row per actor/project/role while different roles can be issued
concurrently. Regrant after revocation creates new immutable history. Issue
idempotency hashes the requested role; revoke derives the role from the locked
grant. Same key/different role mismatches, new-key duplicate same-role issue is
a stable audited conflict, and replay reauthorizes before disclosure.

AUTH-10 replaces current typed and PostgreSQL validators in migration `0027`
without editing `0018`, `0019`, or `0022`. It fails closed if obsolete combined
or replacement evidence exists and refuses an unsafe downgrade rather than
converting or deleting evidence. Only issued and revoked success events remain.
Linked invalidation preserves exact grant, actor, project, role, and cause.
Submitter revocation alone can enter AUTH-13 assignment reconciliation;
reviewer revocation may create only its exact REV-owned review obligation.
Adjudicator revocation persists exact invalidation only: it creates or consumes
no adjudication obligation until WS-REV separately defines that lifecycle and
AUTH activates its exact actions. No role revocation changes another project
role or an AdminRoleGrant. The adjudicator grant provides only exact-project
visibility until that separate activation.

## D22: Fixed service runtime admission is separate from human admission

Status: accepted by the user on 2026-07-16 and supersedes D7's conflicting
ActorProfile clause while retaining its explicit-system-authority rule.

Every protected service command resolves a verified service subject through an
active identity link and service ActorProfile, validates the fixed
`service_identity`, and selects only its exact static ActionId row. It never
enters human first-access provisioning or human grant evaluation. AUTH-09E owns
this admission path but activates no feature operation.

## D23: Merged WS-XINT handoffs supersede stale AUTH boundary wording

Status: accepted through merged PR #139 on 2026-07-17.

The canonical AUTH/ART, AUTH/REV, AUTH role/service, ART/REV, and REV/CON
handoffs are binding planning inputs. AUTH owns grants, decision evidence,
evaluator integration, and action availability. Feature owners retain resource
facts, guards, hidden behavior, and product state. Request routes or service
commands own one transaction. Older combined-role, feature-owned activation,
or service-admission wording is not an alternate contract.

PR #132's fixed service foundation remains technically valid: seven artifact
service identities, eleven exact static ActionId memberships, no database
assignment rows, and migration `0023`. Its branch must converge from trusted
`main` without restoring pre-XINT planning text. Convergence must preserve the
packaged frozen migration contract, zero mutable `app.modules` imports from the
migration, explicit Alembic-script-owned repository root, location-independent
built-wheel custody/replay proof, same-event-loop CLI execution and engine
disposal, and original `BaseException` precedence with cancellation/cleanup
tests. The exact converged head then repeats required internal review and
external checks before merge.

## D24: Sensitive cross-module mutations use prepared authorization

Status: adopted by the WS-XINT transaction contract; runtime remains proposed.

`WS-AUTH-001-PREP` introduces an internal, opaque, non-Pydantic, single-use
`PreparedAuthorizationHandle` bound to the exact session, ActionId, actor
reference kind, actor reference, idempotency key, and canonical request digest.
It is never a route schema, caller input, or serialized reference. The existing
`AuthorityClaimHandle` remains a distinct internal idempotency-reservation
contract and is not the PREP handle. When final-admin safety applies, AUTH locks
`AuthorityControl(id=1)` first. It orders multiple authority
principals by `ActorProfile.id`; for each human it locks `ActorProfile`, the exact
`ActorIdentityLink`, then the exact matched admin or project grant; for each
service it locks `ActorProfile` then the exact `ActorIdentityLink`. It validates
the code-owned `service_identity`, static matrix membership, and action
availability after those locks; those values are not database lock targets. The
feature locks its records only after all authority rows, recomposes final typed
facts, and asks AUTH to evaluate exactly once and stage decision evidence.
Feature participants flush, and the route or service command commits once.
Reads retain `require()`. Before any feature mutation, consumption requires an
exact match on every handle binding. Reuse, cross-session/action use,
same-session/action cross-actor or cross-request substitution, authority loss,
evidence failure, participant failure, cancellation, and commit failure leave no
feature mutation or partial evidence. AUTH never imports a feature repository.

## D25: ActionOwner is an exact AUTH activation custodian

Status: accepted through merged PR #139; runtime transfer remains proposed.

`ActionOwner` no longer names a resource-owning feature chunk. The exact
availability-neutral transfers and future activation groups are canonical in
`ACTIVATION_CUSTODY.md`. `WS-AUTH-001-ART-CUSTODY` atomically transfers all 25
current ART rows to eight AUTH groups and removes seven ART owner values.
`WS-AUTH-001-REV-CUSTODY` atomically transfers all 19 current REV rows to seven
AUTH groups and removes seven REV owner values. Counts, mappings, and planned
availability remain unchanged; no migration is required for owner metadata.

Every activation requires an immutable merged feature manifest, real-kernel
unavailable proof before activation, exact evaluator integration, and one exact
availability delta afterward. ART/REV/CON cannot activate actions, and AUTH-12,
AUTH-14, and AUTH-15 are not fallback activation paths.

## D26: Proposed cross-initiative actions register only after complete contracts

Status: exact identifiers approved by PR #139; registration remains blocked.

The four proposed REV lifecycle actions and
`artifact.review_evidence.binding.create` are not current runtime actions. AUTH
registers them only in separate reviewed chunks after feature owners publish
principal, typed context, facts, guards, surfaces, transaction ownership, and
hidden dependency manifests. Registration is planned and availability-neutral,
uses existing PermissionIds, and adds typed/PostgreSQL evidence parity.

The review-evidence binding action extends only
`workstream.artifact.binding`, making 12 exact matrix memberships across the
same seven identities. Its activation requires separate human and service
decisions, two evidence records, explicit lock order, and one transaction; a
human request is never silently converted to service authority. REV timer,
expiry, reconciliation, projection, artifact-reference, and release-control
services require later exact identity-specific contracts. No catch-all service
identity is pre-created.

## D27: Each remaining AUTH surface owns exact action and migration parity

Status: planning repair required before each future chunk starts.

AUTH-10 through AUTH-15 must enumerate every new ActionId, retained
PermissionId mapping, canonical target, principal class, candidates, guards,
surface, and revalidation rule before runtime edits. Each owning migration
updates current typed and PostgreSQL audit validation; no chunk may promise an
active surface whose ActionId is absent. AUTH-11 therefore owns migration
`0028`, and later migration reservations shift through AUTH-15 as superseded
by D30. AUTH-16 aggregates proof; it does not discover or backfill missing
registrations.

## D28: Service provisioning records an unverified issuer binding

Status: accepted as required AUTH-09B preimplementation repair on 2026-07-17.

The provisioning administrator selects one fixed `ServiceIdentity` and supplies
one opaque subject with no leading or trailing whitespace. Accepted subject
bytes are preserved without normalization. The issuer is server-owned
configuration exposed through the provider-neutral `AuthVerifier` port. It
never comes from request input, provider branching, fallback configuration, or
the administrator's own identity link.
The identity digest consumes that exact already-validated issuer without a new
scheme restriction, normalization step, or provider-specific path.

Provisioning is not proof that the service presented a token. AUTH-09B migration
`0024` therefore makes `ActorIdentityLink.last_verified_at` nullable only for
service links, removes its implicit default, and requires human links to remain
verified. Human first access writes database time explicitly. New service
profiles and links keep `last_seen_at` and `last_verified_at` null until AUTH-09E
successfully verifies that exact service token. The migration allocation then
shifted AUTH-10 through AUTH-15 to `0025` through `0030`; D29 supersedes only
that future allocation after ART claimed the next trusted-main head. Historical
migrations remain immutable.

Both central AUTH and legacy actor dependencies reject service subjects before
actor resolution or timestamp mutation until AUTH-09E. Provisioning a service
therefore cannot make an existing legacy route an alternate service-admission
path.

The administrative mutation locks `AuthorityControl`, caller profile, exact
caller link, and matched system Access Administrator grant before fixed service
identity and external issuer/subject advisory locks. All canonical human lock
helpers use profile-before-link order. Success advances only the human caller's
verification timestamps. Replay reauthorizes and advances only that caller;
mismatch, denial, conflict, or failure advances neither caller nor service.

Service creation keeps the current `effective=true -> false` authority
invalidation direction because the new binding invalidates cached negative
identity-absence projections. It does not claim that a service permission was
previously or is now executable. AUTH-09E remains the only runtime service
admission owner.

## D29: ART `0025` shifts future AUTH migration custody

Status: accepted cross-initiative reconciliation on 2026-07-17.

AUTH-09B remains the immutable owner of migration `0024`. WS-ART-001-02A3 owns
migration `0025` for the ArtifactStore v2 clean cut. Future, inactive AUTH
reservations therefore shift exactly once: AUTH-10 owns `0026`, AUTH-11 owns
`0027`, AUTH-12 owns `0028`, AUTH-13 owns `0029`, AUTH-14 owns `0030`, and
AUTH-15 owns `0031`.

This decision supersedes only the future migration-number allocations in D15,
D27, and D28. It does not modify any merged migration, action ownership,
authorization behavior, or feature activation boundary.

## D30: Split lifecycle mutations and repair evidence before activation

Status: accepted preimplementation repair on 2026-07-18.

Required L1 review rejected the combined AUTH-09D contract before runtime
edits. The parent is split semantically: AUTH-09D-A owns lifecycle evidence
repair plus profile suspend, reactivate, and terminal deactivate; AUTH-09D-B
later owns identity-link revoke/reactivate plus the mixed profile/link/grant
race closure. Each child requires its own explicit gate, review, merge intent,
PR, merge, and signed-memory stop.

The existing database and typed lifecycle evidence force every non-admin
transition from effective to ineffective. That is false for profile and link
reactivation, and ActorProfile lacks durable reactivation provenance. AUTH-09D-A
therefore owns forward migration `0026_actor_profile_lifecycle`; historical
migrations remain immutable. AUTH-10 through AUTH-15 shift to `0027` through
`0032`. This supersedes only D29's future inactive reservations.

Lifecycle routes reserve idempotency before authorization, retain the canonical
singleton/caller-first authorization locks, and disclose target existence only
after an exact permission match. The singleton serializes every lifecycle or
grant path that can remove the final effective Access Administrator, so no
target-first alternate lock path is introduced. Profile and link reactivation
invalidate from ineffective to effective; loss transitions invalidate from
effective to ineffective.

## D31: Prioritize the contributor/canonical-human foundation after AUTH-09D-B

Status: accepted sequencing reconciliation on 2026-07-18.

The prior plan left assignment ownership renaming in AUTH-13 and Submission
ownership renaming in AUTH-14. That creates an unnecessary dependency cycle:
REV needs canonical human attribution before its first runtime child, while the
full AUTH-13/14 product cutovers depend on later REV preparation behavior.

`WS-AUTH-001-CONTRIBUTOR-FOUNDATION` is therefore the next same-initiative gate
after AUTH-09D-B and before AUTH-09E. It clean-cuts only the two ownership fields,
adds reusable database-backed human ActorProfile lineage, and exposes bounded
transaction-local active-human revalidation. It changes no permission, action,
grant, lifecycle, or feature availability. AUTH-13/14 retain their later
authorization and lifecycle cutovers and consume the canonical fields.

The foundation allocates only the then-current next migration from trusted
`main`. This decision supersedes only the future fixed-number reservation
clauses in D29, D30, and earlier decisions; their other boundaries remain in
force. Merged migration ownership through AUTH-09D-A `0026` is unchanged.
