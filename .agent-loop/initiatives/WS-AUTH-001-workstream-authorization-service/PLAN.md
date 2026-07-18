# Plan: WS-AUTH-001 - Workstream Authorization Service

## Goal

Replace the token-role bootstrap with the adopted Workstream-owned actor,
grant, permission, scope, guard, revocation, and audit model while preserving
the proven intake lifecycle and historical actor attribution.

## Adopted authority flow

```text
Bearer token
-> TokenVerifier
-> VerifiedIssuerToken
-> ActorResolver
-> ActorIdentityLink + ActorProfile
-> request-scoped AuthorizationContext
-> AuthorizationService.require(ActionId, typed ResourceContext)
-> AdminRoleGrant / ProjectRoleGrant candidates
-> canonical project and ownership resolution
-> actor, resource, and lifecycle guards
-> allow or stable denial code
```

Token roles are never included as product authority.

Sensitive mutations use a second phase after authentication and candidate
resolution:

```text
AUTH locks current authority and returns one prepared handle
-> feature locks canonical rows and recomposes final typed facts
-> AUTH evaluates once and stages evidence
-> feature participants flush
-> route or service command commits once
```

Fixed services use a structurally separate context resolved from an active
identity link, active service ActorProfile, immutable `service_identity`, exact
static ActionId row, and active action. They never enter human first access or
grant evaluation.

## Migration strategy

### Legacy classification and actor identity

The final model has one canonical `ActorProfile` and one active-or-revoked
`ActorIdentityLink` per profile. Existing externally verified actor IDs are
UUID5 strings. After explicit classification and UUID validation, that UUID is
preserved as the canonical `ActorProfile.id`; the identity link receives a new
UUID. Existing typed profile row IDs are unrelated workflow IDs and are not
promoted into actor identity or authority grants.

The actor migration must not guess `subject_kind`. For a non-empty persistent
registry, a versioned JSON classification manifest is validated through a
supported management tool against exact actor ID, issuer, and subject. The tool
rejects stale, missing, duplicate, mismatched, and unknown entries, supports
dry-run, and produces a checksum-bound evidence report. The migration consumes
only validated staged evidence; otherwise deployment fails with a precise
remediation report. Empty and test databases migrate normally.

Historical actor references remain string identifiers in early chunks because
a broad FK rewrite is not required to establish correct authority. Runtime
services nevertheless use explicitly provisioned service ActorProfiles before
executing protected commands.

### Authorization cutover

The implementation introduces the canonical service before moving product
surfaces. Each cutover chunk migrates a complete resource family and removes
its old issuer-role authorization. No command accepts issuer role metadata or local grant
as alternate sufficient proof.

Project configuration moves first because it is required to create project
grants and to prove authorization before separately starting `WS-POL-002-04`.
This initiative does not own or advance PR #90. Task/submission/checker access
follows after exact-project contributor grants and resource loaders exist.

Project contributor grants are independent immutable `submitter`, `reviewer`,
and `adjudicator` rows. AUTH-10 removes current `both` and replacement paths
from typed and PostgreSQL validation in a clean cut. It does not rewrite old
migrations, convert ambiguous evidence, or let one revocation alter another
project role or an AdminRoleGrant.

Every cutover chunk enumerates its exact ActionIds before implementation and
updates current typed/PostgreSQL audit mapping validation in its own migration.
After AUTH-09A migration `0023`, AUTH-09B uses `0024` for service-link
verification timestamp semantics and ART owns `0025` for the ArtifactStore v2
clean cut. Core reservations are AUTH-10 `0026`, AUTH-11 `0027`, AUTH-12
`0028`, AUTH-13 `0029`, AUTH-14 `0030`, and AUTH-15 `0031`.
Blocked cross-initiative additions allocate the next trusted-main migration head
only when their complete feature contracts become executable. No migration
number is reserved or allocated while the work remains blocked.

Chunk 06 preserves task claim/start/submission operability through an explicitly
named `LegacyWorkflowEligibilityCompatibility` adapter. It reads only
classified legacy workflow metadata, grants no product permission, and is
limited to enumerated task-service call sites. Chunk 13 removes it from task
queue/claim/start, chunk 14 removes its final submission consumer, and chunk 15
proves the adapter and allowlist removed in chunk 14 remain absent. No merged intermediate state may
require a deleted typed-profile registry.

### Request context, idempotency, audit, and errors

Introduce request and correlation context, canonical mutation idempotency, the
shared authority-event writer, and a stable error envelope with canonical actor
persistence before grant-management APIs. Every authority mutation commits its
state, idempotency result, audit event, and invalidation event in one database
transaction. Events record the acting and target profiles, matched grant,
project, reason, idempotency key, and bounded before/after state. Raw tokens,
JWKS documents, and full provider claims are never persisted.

The shared audit path is append-only through supported application APIs and
database enforcement. Each authority-mutation chunk proves its specified
allowed and denied events when the behavior is introduced; chunk 16 may verify
completeness but may not create or backfill missing evidence.

### System work

Internal Celery work uses fixed Workstream principals and explicit registered
system permissions. Requester identity serialized into a job remains audit
evidence only. Actor-attributed mutations reload current profile and grant
state before commit.

AUTH-09A's seven artifact identities and eleven exact matrix memberships remain
the first closed service set. New REV or CON services are not inferred or
grouped into a catch-all: each owning feature must first publish an exact
identity-to-ActionId manifest, followed by a reviewed AUTH constraint, matrix,
provisioning, admission, and cross-service denial extension.

### Ownership and transaction boundaries

- The existing `AuthVerifier` port/factory evolves in place; there is no second
  token-verifier hierarchy.
- Canonical ActorProfile/ActorIdentityLink persistence stays in `actors`.
- Admin/project grants, permission definitions, idempotency, invalidation, and
  authorization evaluation stay in `authorization`. Qualification snapshots
  are owned by authorization with project ownership enforced through existing
  project relationships.
- `ProjectRepository` and `TaskRepository` remain the canonical persistence
  loaders for their domain records. Project/task application services or
  feature-owned resource loaders compose `ResourceContext` from those records;
  persistence repositories do not depend on authorization DTOs, and
  authorization does not duplicate project/task queries.
- Existing `AuditEvent` and `AuditRepository` evolve into the shared authority
  evidence path; no parallel authority-event ledger is added.
- The injected AsyncSession is the UnitOfWork boundary. The request route or
  service command owns commit/rollback; AUTH and feature participants flush
  only. Dependency teardown never commits an arbitrary shared transaction.
- Sensitive cross-module mutations use the opaque prepared protocol from
  `WS-AUTH-001-PREP`; AUTH locks authority first but never imports feature
  repositories or commits feature state.

### Test preservation rule

Current intake lifecycle tests may not be deleted, skipped, xfailed, or have
their lifecycle assertions loosened. As surfaces migrate, positive
authorization fixtures must provision canonical profiles, links, and grants
through supported service/API paths and exercise the real ActorResolver,
FastAPI dependency, and AuthorizationService. Dependency overrides, fabricated
ActorContext objects, issuer-role fallbacks, and direct database grant inserts
are not valid product-authorization proof. Direct row factories remain limited
to repository and migration tests. Every migrated surface adds a negative test
proving the same issuer role metadata alone no longer authorizes.

## Implementation sequence

1. Adopt and reconcile the specification baseline, API namespace, ADRs, durable
   loop state, checksum evidence, and auth operations ownership.
2. Implement the verified issuer-token/JWKS/introspection boundary with
   fail-closed configuration and deterministic fixtures.
3. Implement the versioned legacy-actor classification preflight and rollout
   evidence workflow.
4. Establish request/correlation context, structured errors, and API rate
   controls.
5. Evolve shared audit evidence in 05A, then add canonical
   idempotency/invalidation in 05B.
6. Migrate to canonical profile/link semantics and first-human resolution.
7. Register the closed permission/action catalogue with audit parity in 07A,
   then implement the minimal AuthorizationService kernel and canonical actor
   self-action cutover in 07B before protected authority-management APIs.
8. Implement bootstrap, `AuthorityControl`, and immutable admin-role grants.
9. Reconcile merged WS-XINT boundaries and converge AUTH-09A on trusted `main`.
10. Complete the uninterrupted AUTH-09B through 09E sequence: controlled
    provisioning, actor/link administration, lifecycle mutations, and fixed
    service runtime admission without activating feature actions.
11. Transfer all current ART/REV owner labels to exact AUTH custodians without
    changing availability, then add the prepared mutation authorization
    protocol.
12. Implement qualification snapshots and independent contributor grants scoped
    to the exact project, including the typed/PostgreSQL clean cut from `both`
    and replacement evidence.
13. Cut project identity, guide, source, and visibility queries over to local
   permissions.
14. Cut project policy mutations, approvals, activation, and setup operations
    over to local permissions.
15. Cut task management, queue, assignment, claim, and start operations over.
16. Cut submission, pre-submit, checker trigger/read, and task audit visibility
    over.
17. Cut remaining internal services over, verify the project-setup cutover,
    remove old runtime authority, and enforce a
    deterministic stale-authority scanner.
18. As ART, REV, and CON hidden manifests merge, run only their exact AUTH
    registration and activation chunks from `ACTIVATION_CUSTODY.md`.
19. Complete privacy/observability, full conformance, concurrency, and live
    proof after every exposed protected surface has matching activation and all
    unimplemented planned actions still deny.

## Alternatives rejected

- Treating issuer roles as local grants.
- Automatically converting observed worker/reviewer/admin profiles to grants.
- Keeping both `ActorIdentity` and a new canonical `ActorProfileV2` as roots.
- Adding a generic policy-language engine.
- Caching authorization decisions across requests.
- Changing to `/v1` or exposing permanent `/v1` aliases.
- Activating review lifecycle work before its AUTH, ART, and CON proof. Hidden
  feature behavior may be built in parallel while the real kernel denies the
  planned action.

## Boundaries preserved

- Existing module organization remains feature-oriented:
  `router -> service -> repository -> models/schemas`.
- No repo-wide domain/persistence directory rewrite.
- No Workstream login/session/token issuance.
- No review, contribution, compensation, frontend, blockchain, or external
  source-adapter implementation.
- No change to canonical review decision values.
- No weakening of CI, tests, auth defaults, or internal-review requirements.

## Verification strategy

### Per chunk

- Ruff and focused tests.
- Migration forward/backward and constraint proof when schema changes.
- Negative authorization tests for every added permission path.
- Stale wording, Markdown links, and `git diff --check`.
- Required internal reviewers and PR trust bundle.

For every schema chunk, verification includes an isolated-test-database
`alembic upgrade head -> downgrade -1 -> upgrade head` round trip plus focused
migration assertions. For every chunk, post-review closure separately requires:

```bash
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
```

These run after reviewer evidence and memory/status updates exist; they are not
pre-review implementation substitutes.

### Initiative exit

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_stale_authorization_docs.py
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/auth_api_e2e.py)
(cd backend && .venv/bin/docstr-coverage --config .docstr.yaml)
git diff --check
```

The auth live drill must prove first human access, one-time bootstrap, scoped
admin grants, independent project submitter/reviewer/adjudicator grants,
concurrent three-role issue, independent revoke/regrant in every direction,
wrong-grant denial, submitter-only assignment invalidation, separation of
duties, revocation using the same unexpired token, transaction-time authority
loss, suspension/reactivation, fixed-service admission and cross-service denial,
prepared-handle rollback, action-owner/mapping/availability parity,
feature-manifest-before-activation ordering, cross-project denial, and
final-admin concurrency safety.

## Documentation strategy

The baseline-adoption chunk adds an ADR before changing implementation and
reconciles README, glossary, architecture lockdown, role/permission operations,
data model, and imported specification route examples. The eight imported files
remain immutable archival planning inputs with durable hash evidence. A
reference README records their status and `/api/v1` override. Canonical
reconciled authorization text is maintained separately; a canonical PDF is
generated only when a deterministic repository build command exists.

A deterministic documentation scanner uses an explicit historical/archive
allowlist and rejects non-`/api/v1` route references plus obsolete authority
claims in active docs. It does not use bare `rg` success semantics.

`docs/operations_authorization_service.md` owns issuer/JWKS configuration,
rotation and outage response, cache/introspection policy, bootstrap custody,
legacy classification, staged rollout/rollback, alert response, and live-proof
responsibility. Each implementation chunk updates the relevant section.

Payment/reputation contradictions discovered in the broader reference set are
recorded but remain outside this auth initiative. They require their own later
ADR and initiative before contribution/compensation implementation.

## Stop conditions

Stop the active chunk if:

- issuer behavior requires trusting a token role or unverified claim;
- actor migration requires guessing legacy subject kind;
- a second canonical actor or authorization path is required;
- project scope cannot be derived from canonical database relationships;
- a migration cannot preserve existing lifecycle data;
- CI or existing intake tests must be weakened;
- production credentials, private keys, or production data are required;
- scope expands into review, compensation, frontend, or external settlement.
