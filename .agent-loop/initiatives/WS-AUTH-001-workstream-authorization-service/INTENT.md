# Intent: WS-AUTH-001 - Workstream Authorization Service

## Problem being solved

Workstream currently verifies an external identity token and then treats token
role claims such as `admin`, `project_manager`, and `worker` as product
authority. Authorization is distributed across module services through
`require_any_role()` and local object checks. The current actor registry also
models one external identity with multiple role-shaped profile rows.

That bootstrap is incompatible with the adopted
`WS-AUTH-001` authority contract. Workstream must own actor state,
administrative grants, project contributor grants, permission evaluation,
resource guards, revocation, and authorization evidence.

## Why this work matters

Review, contribution, compensation, and external adapter work all depend on a
trustworthy local authority spine. Continuing to add APIs to the token-role
bootstrap would expand a security model that has now been explicitly
superseded.

## Current behavior

- External issuer and subject identify an `ActorIdentity`.
- Verified token role claims populate `ActorContext.roles`.
- `require_any_role()` uses those claims as route authority.
- Multiple typed `ActorProfile` rows hold observed or active workflow metadata.
- Project-manager authority is not represented by durable project-scoped
  grants.
- Production JWKS verification, local authority revocation, actor suspension,
  service-subject provisioning, and final-access-administrator protection are
  absent.

## Target behavior

- Identity Issuer tokens establish authentication and coarse access only.
- One `(issuer, subject)` resolves through one active `ActorIdentityLink` to
  one canonical `ActorProfile`.
- Human first access provisions an active Contributor-domain actor without
  product authority.
- Service subjects require deliberate provisioning; agent and Space subjects
  are denied in v0.1.
- Workstream-owned `AdminRoleGrant` and exact-project `ProjectRoleGrant`
  records provide permission candidates.
- ProjectRoleGrant roles are independently persisted as `submitter`,
  `reviewer`, and `adjudicator`; the adjudicator grant creates no adjudication
  capability until WS-REV defines the lifecycle and AUTH activates exact
  adjudication actions.
- Explicitly provisioned service subjects resolve through service
  ActorProfiles and a closed static service-action matrix, never human grants.
- One `AuthorizationService` combines registered permissions, grant scope,
  canonical resource ownership, actor state, lifecycle state, and explicit
  guards.
- Sensitive mutations use an AUTH-first prepared handle, feature-owned final
  fact recomposition, one authorization evaluation, and one caller-owned commit.
- `ActionOwner` names one exact AUTH activation custodian; ART, REV, CON, and
  product modules keep resource facts and behavior but never change action
  availability.
- Revocation and suspension take effect from database state without requiring
  token refresh.
- Sensitive authority changes are idempotent, concurrency-safe, and auditable.
- All product APIs remain under the existing `/api/v1` namespace.

## Design chosen

Evolve the existing auth and actor boundary into the adopted model. Preserve
stable historical actor identifiers when the legacy row can be explicitly and
safely classified. Do not add a parallel `ActorProfileV2` or retain token-role
authorization as an alternate path.

Implementation is split into PR-sized chunks. Token verification and canonical
actor resolution precede grants. Grants precede centralized permission
evaluation. Existing project, task, submission, checker, and contributor surfaces
move to the new authorization service in bounded cutover chunks.

## Alternatives considered

### Keep issuer role metadata and add project grants

Rejected. Issuer role metadata would remain a second authority source and revocation
would still depend on token lifetime.

### Add a parallel authorization subsystem

Rejected. Two actor/profile and permission systems would create ambiguous
authority and unsafe partial migrations.

### Rewrite all protected surfaces in one PR

Rejected. The blast radius is too large for careful migration, review, and
rollback analysis.

### Change all APIs to `/v1`

Rejected by human decision. `/api/v1` is the existing tested compatibility
namespace and remains canonical.

## Boundaries preserved

- Workstream verifies external Flow/Identity Issuer tokens; it does not own
  login, passwords, primary sessions, or token issuance.
- Postgres remains canonical for product authority.
- Existing project, task, submission, and checker lifecycle rules remain in
  their owning services and become authorization resource guards where needed.
- The proven intake path through `review_pending` remains operational and
  regression-tested.
- System-owned recovery work uses explicit internal principals and never
  fabricates human authority.
- Review, contribution, compensation, frontend, blockchain settlement, and
  external source adapters are out of scope.

## Expected risks

- Accidentally accepting issuer role metadata after local grants are introduced.
- Misclassifying legacy actor rows that lack `subject_kind` provenance.
- Leaving a protected endpoint on the old authorization path.
- Breaking historical actor attribution during schema migration.
- Losing the final Access Administrator under concurrent mutations.
- Cross-project authorization through client-supplied resource scope.
- Leaking identity claims, token material, or hidden resource existence.
- Building new approval endpoints on the obsolete bootstrap during cutover.
- Coupling submitter, reviewer, and adjudicator authority into one grant row.
- Allowing a service token to enter human first-access or grant evaluation.
- Letting a feature label remain an activation owner after PR #139.
- Registering or activating review/artifact actions before complete feature
  manifests and transaction proof exist.
- Retaining `both` or replacement evidence in current typed or PostgreSQL
  validators after independent project-role grants ship.

## What must not change

- External authentication ownership.
- Canonical review decisions: `accept`, `needs_revision`, `reject`.
- Immutable submission/checker provenance.
- Existing task lifecycle behavior except the explicit, audited release of an
  exclusive assignment when its actor/link/project authority is invalidated.
- CI, test, documentation, and internal-review gates.
- `WS-POL-002-03` remains independently owned by PR #90; this initiative does
  not activate `WS-POL-002-04` before authorization proof and a separate start.

## How this will be proven

- Unit tests for token, permission, and guard contracts.
- PostgreSQL migration, uniqueness, row-locking, idempotency, and concurrency
  tests.
- Table-driven permission matrix tests.
- Negative cross-project, self-grant, self-review, inactive-actor, service,
  agent, and Space tests.
- Existing project/task/checker regression suite and API contract drill.
- A live API authorization drill proving bootstrap, grants, revocation with the
  same token, suspension/reactivation, and final-admin safety without direct
  database edits.

## Human decisions required

Resolved:

- `WS-AUTH-001` is authoritative and supersedes the token-role bootstrap.
- `/api/v1` remains the canonical API namespace.
- `WS-AUTH-001` is prioritized before `WS-POL-002-03`.
- D4-D10 were explicitly approved and `WS-AUTH-001-01` was started by the user
  on 2026-07-11 after planning and post-merge memory closed.
- D20-D22 establish service ActorProfiles, independent three-role project
  grants, and fixed service runtime admission.

External deployment details such as issuer URL, JWKS URL, approved algorithms,
claim names, and introspection policy are configuration inputs. Their absence
does not block deterministic adapter implementation and tests, but it does
block the production live-token proof.

## Initial risk class

L0 for initiative direction, auth model, and data-model strategy. D1-D10 are
human-approved. Subsequent bounded implementation chunks are L1 and require
their own chunk contracts, evidence, reviewer fanout, and human checkpoints.
