# ADR 0012: Workstream Owns Product Authorization

## Status

Accepted on 2026-07-11.

## Context

ADR 0006 correctly keeps login, signup, password storage, password reset, and
primary sessions outside Workstream. The current backend nevertheless uses
verified token role claims and typed workflow profiles as temporary product
authority. That bootstrap cannot express durable project scope, immediate
revocation, one-time administrator bootstrap, final-administrator safety,
service principals, or complete authority evidence.

The adopted WS-AUTH-001 reference specification defines the target actor,
grant, permission, scope, guard, revocation, and audit model. Its examples use
a shorter version prefix; this repository already exposes `/api/v1` and will
not maintain two permanent versioned route trees.

## Decision

Workstream continues to verify externally issued Flow tokens. A verified token
proves issuer identity, subject identity, subject kind, audience, time bounds,
and coarse request scope. It does not assign a Workstream product role.

Workstream owns product authorization through:

- one canonical `ActorProfile` per actor;
- `ActorIdentityLink` records for verified issuer/subject identities;
- immutable `AdminRoleGrant` and `ProjectRoleGrant` history;
- a registered permission catalog;
- exact system/project scope resolution from canonical database records;
- actor, grant, resource, assignment, separation-of-duties, and lifecycle
  guards;
- immediate revocation and transaction-time revalidation for sensitive writes;
- append-only authority events, canonical idempotency, and invalidation events.

The canonical request flow is:

```text
external bearer token
-> existing AuthVerifier boundary
-> VerifiedIssuerToken
-> ActorResolver
-> ActorProfile + ActorIdentityLink
-> AuthorizationContext
-> AuthorizationService.require(ActionId, typed ResourceContext)
-> candidate grants
-> resource and lifecycle guards
-> allow or stable denial
```

Token roles never enter `VerifiedIssuerToken` as product authority. During the
bounded migration, an explicitly named compatibility context may expose
verified legacy role claims only to an enumerated shrinking set of unmigrated
call sites. A migrated surface cannot accept token role and local permission as
alternative sufficient proof.

The repository keeps `/api/v1` canonical. Short-prefix examples in archival
inputs are not routes and no permanent alias will be added.

## Roles And Grants

Administrative grants are:

- `access_administrator`
- `operator`
- `project_manager`
- `finance_authority`
- `audit_authority`

Contributor project grants are:

- `submitter`
- `reviewer`
- `adjudicator`

ADR 0015 supersedes the earlier combined-role design. These capabilities are
independently granted.

Contributor is the umbrella human product term. A contributor may hold separate
exact-project `submitter`, `reviewer`, and `adjudicator` grants. The adjudicator
grant creates no adjudication capability in v0.1; a future separately approved
initiative must define the lifecycle before AUTH can register and activate any
exact adjudication action. Celery, checker, setup, and
background workers are internal services, not human product roles.
Administrative roles alone do not authorize submission, review, or
adjudication.

The three additive Operator recovery permissions approved with this ADR are:

- `operations.task.start_override`
- `operations.submission_gate.repair`
- `operations.checker.retry`

Normal covered Project Manager repair remains `project.task.manage`.
`review.lease.force_release` remains owned by the review specification. Broad
historical statements such as “admin override” are not executable permissions
and cannot bypass immutable submissions, checker evidence, review decisions,
contribution records, or compensation guards.

## Identity And Migration

Existing externally verified `ActorIdentity.actor_id` UUID5 values may become
canonical `ActorProfile.id` values only after exact issuer/subject
classification and UUID validation. Legacy typed profile row IDs never become
canonical actor IDs. Existing typed contributor, reviewer, admin, or
project-manager profiles do not become grants.

Non-empty persistent actor registries require the versioned, checksum-bound
legacy classification process defined by the WS-AUTH-001 plan. Migration must
fail closed rather than infer human/service kind, authority, or grants from
email, subject shape, profile type, or token roles.

## Bootstrap And Revocation

The first Access Administrator is established through a one-time local
management operation, never a public bootstrap endpoint or shared bootstrap
secret. Bootstrap and every operation that could remove the final effective
Access Administrator serialize on `AuthorityControl(id = 1) FOR UPDATE` and
write authority evidence atomically.

Suspension, deactivation, identity-link revocation, and grant revocation take
effect on the next request. Sensitive transactions reload and revalidate
current authority before commit. Revoked grants and links remain immutable
history.

## Evidence And Transactions

The injected SQLAlchemy `AsyncSession` is the unit-of-work boundary. An
authority mutation commits business state, idempotency result, append-only
authority event, and invalidation event in one transaction. Raw tokens, full
claim payloads, JWKS bodies, secrets, artifact bytes, and unnecessary personal
data are never stored as authority evidence.

## Specification Precedence

- ADR 0006 remains authoritative for external authentication ownership.
- WS-AUTH-001 and this ADR own actor identity, grants, authorization, and
  authority evidence.
- WS-REV-001 owns review routing, leases, review decisions, and revision guards.
- `docs/spec_review_lifecycle.md` is the active review/revision implementation
  contract; archival WS-REV files are non-executable inputs.
- WS-CON-001 owns contribution and compensation boundaries.
- Human review decisions remain exactly `accept`, `needs_revision`, and
  `reject`.

When older active documentation uses `admin`, `project_manager`, token-role, or
typed-profile language as route authority, this ADR supersedes that authority
statement. Historical implementation records may retain the old wording only
when explicitly classified by the stale-authorization documentation gate.

## Consequences

Positive:

- authorization becomes local, scoped, revocable, auditable, and testable;
- external authentication remains outside Workstream;
- project authority no longer depends on mutable token role claims;
- system recovery and human authority remain distinct;
- later review/contribution work receives stable actor and permission inputs.

Tradeoffs:

- the cutover requires staged migrations and temporary compatibility paths;
- production issuer/JWKS/introspection configuration and legacy actor
  classification are deployment inputs;
- each resource family must remove old authority only after its local grants and
  guards are proven.

## Out Of Scope

This ADR does not implement login, runtime authorization, migrations, review,
contribution, compensation, frontend behavior, blockchain settlement, external
source adapters, automated routing, or an agent workspace.
