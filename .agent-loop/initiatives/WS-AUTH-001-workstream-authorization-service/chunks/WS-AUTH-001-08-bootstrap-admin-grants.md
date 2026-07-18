# Chunk Contract: WS-AUTH-001-08 - Bootstrap And Administrative Role Grants

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Implement the one-time local Access Administrator bootstrap, the closed
administrative role/permission definitions, immutable `AdminRoleGrant`
history, grant-backed central authorization, scoped read/issue/revoke APIs,
idempotency, and concurrency-safe final-administrator protection.

## Why this chunk exists

Workstream needs durable administrative authority before actor administration,
project grants, or product surfaces can stop using token roles. AUTH-07B left
only actor self actions active; this chunk adds the exact administrative trust
root and no product cutover.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/PLAN.md`
- DECISIONS: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/DECISIONS.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/actors/**
backend/app/modules/authorization/**
backend/app/modules/audit/**
backend/app/modules/projects/repository.py
backend/app/api/deps/authorization.py
backend/app/api/routes/auth.py
backend/app/api/router.py
backend/app/db/models.py
backend/scripts/bootstrap_access_administrator.py
backend/scripts/api_contract_e2e.py
backend/alembic/versions/0022_*.py
backend/tests/test_authorization.py
backend/tests/test_audit.py
backend/tests/test_auth.py
backend/tests/test_actors.py
backend/tests/conftest.py
backend/tests/test_alembic.py
backend/tests/test_api_controls.py
backend/tests/test_api_rate_controls.py
backend/tests/test_app.py
backend/tests/test_projects.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/operations_roles_permissions.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-08.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
public bootstrap endpoint or shared bootstrap bearer secret
project contributor grants or qualification state
actor/link lifecycle mutation APIs owned by AUTH-09
product surface cutover
self-grant or self-revoke
service actors receiving human administrative grants
deleting grants or audit/idempotency history
token-role authority, client-supplied permissions, or request-supplied project authority
cross-request decision cache, second policy engine, or second product-authority/mutation
unit of work; the preexisting independently committed durable rate-control
session remains an outer API control
CI workflow, dependency, coverage-floor, skip, xfail, or exclusion changes
```

## Exact action additions and surfaces

AUTH-08 adds exactly seven `ActionId` values, an `AUTH_08` owner, and seven
active catalogue rows. The catalogue becomes exactly 57 actions, of which only
the two AUTH-07B actor-self actions and these seven AUTH-08 actions are active.
No PermissionId is added or renamed. Each action has one canonical target,
candidate source, guard set, and principal type; definition reads, scoped
history reads, human mutations, and the local trust-root command never share an
ActionId.

| Surface | ActionId | PermissionId | Primary typed resource | Candidate | Guards and revalidation |
|---|---|---|---|---|---|
| `GET /api/v1/authorization/permissions` | `authorization.permission_catalogue.read` | `admin_role.read` | system `permission_catalogue` definition | system Access Administrator or system Audit Authority | exact registered definitions only; no grant or personal data |
| `GET /api/v1/authorization/admin-role-definitions` | `authorization.admin_role_definitions.read` | `admin_role.read` | system `admin_role_definitions` definition | system Access Administrator or system Audit Authority | exact five-role matrix and scope compatibility only |
| `GET /api/v1/admin-role-grants` | `admin_role_grant.list` | `admin_role.read` | canonical system or exact-project grant collection | system Access Administrator; system/exact-project Audit Authority whose scope covers the collection | filter before total/cursor; no broader-scope rows |
| `GET /api/v1/actors/{actor_profile_id}/admin-role-grants` | `actor.admin_role_grant_history.read` | `admin_role.read` | canonical actor grant collection plus required scope selector | system Access Administrator; system/exact-project Audit Authority whose scope covers returned rows | target selector is canonicalized; concealed rows never affect total/cursor |
| `POST /api/v1/admin-role-grants` | `admin_role_grant.issue` | `admin_role.grant` | target-human plus canonical system/exact-project grant selector | system Access Administrator | no self-grant; active human target with at least one active identity link; role/scope compatibility; exact project exists |
| `POST /api/v1/admin-role-grants/{grant_id}/revoke` | `admin_role_grant.revoke` | `admin_role.revoke` | loaded active admin grant | system Access Administrator | no self-revoke; active grant; final Access Administrator remains; caller and matched grant revalidated under lock |
| local bootstrap command manifest | `admin_role_grant.bootstrap` | `admin_role.grant` | fixed bootstrap target-human selector | irreversible `AuthorityControl` bootstrap state, not a human grant | no fabricated bearer context or public kernel bypass; domain evidence only |

Every HTTP operation declares exactly one `x-workstream-action-id`. The local
command exports one typed manifest constant checked against the same catalogue.
Bootstrap does not fabricate an `AuthorizationContext`, matched human grant, or
`SensitiveAuthorizationAllowed` decision. Its deliberate trust-root exception
is confined to the local command and fixed `workstream:system:bootstrap`
principal.

Migration `0022` replaces the PostgreSQL exact action/permission pair constraint
with the 57-pair catalogue and restores the exact 50-pair `0021` constraint on
clean downgrade. Downgrade refuses when any AUTH-08 action evidence or
administrative grant/idempotency history exists.

## Closed administrative role matrix

The implementation exposes one immutable typed mapping from each role to the
following exact PermissionIds. These are permission candidates only; planned
actions remain non-executable while feature owners add hidden canonical
resources/guards and until dedicated AUTH custodians integrate evaluators and
change availability. System scope is never superuser authority.

### `access_administrator`

```text
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
audit.read
audit.export
```

### `operator`

```text
project.read
review.queue.inspect
review.lease.force_release
contribution.read_project
compensation.award.read
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
audit.read
```

The seven artifact permissions above are the complete human Operator artifact
set. Operator receives no artifact ingest, upload, binding-create,
verification-execute, pending-scan, put-resolution, guide-read, checker-input,
or checker-output permission.

### `project_manager`

```text
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
review.queue.inspect
contribution.read_project
compensation.award.read
audit.read
```

`project.create` is a candidate only from a system-scoped Project Manager
grant. Every other candidate is limited to the covered project.

### `finance_authority`

```text
project.read
contribution.read_project
compensation.policy.manage
compensation.adapter_binding.manage
compensation.award.read
compensation.delivery.reconcile
audit.read
```

### `audit_authority`

```text
actor.profile.read_any
actor.identity_link.read
admin_role.read
project.read
project.role_grant.read
review.queue.inspect
review.chain.read
contribution.read_project
compensation.award.read
audit.read
audit.export
```

Access Administrator and Operator grants are system-only. Project Manager,
Finance Authority, and Audit Authority grants may be system-scoped or cover one
exact canonical project. Table-driven tests prove every exact set and every
excluded permission. Only Access Administrator supplies `admin_role.grant` or
`admin_role.revoke`; only Access Administrator and Audit Authority supply
`admin_role.read`, subject to the resource scope above. Audit Authority receives
no `artifact.*` permission: human evidence access is `audit.read`/`audit.export`;
Operator artifact metadata and fixed-service artifact capabilities remain owned
by their existing WS-ART/AUTH-09 contracts.

## Runtime and decision contract

- The feature interface remains exactly
  `await authorization_service.require(action_id, typed_resource_context)`.
- The service remains request-scoped, binds the caller-owned `AsyncSession`,
  and never commits or creates another session.
- The closed strict resource union adds exactly:
  `PermissionCatalogueResourceContext(resource_type,
  resource_id="workstream:permission_catalogue")`;
  `AdminRoleDefinitionsResourceContext(resource_type,
  resource_id="workstream:admin_role_definitions")`;
  `AdminRoleGrantCollectionResourceContext(resource_type, resource_id,
  scope_type, scope_project_id)` where resource ID is the fixed system
  collection or resolved project UUID; `ActorAdminRoleGrantHistoryResourceContext`
  with the target actor UUID plus the same required scope selector;
  `AdminRoleGrantIssueResourceContext` with target actor UUID, role, scope type,
  and optional project UUID; and `AdminRoleGrantResourceContext` with the loaded
  grant UUID for revoke. No generic dictionary or arbitrary system context is
  admitted.
- Because grants are AUTH-owned resources, the central service canonicalizes
  the selected actor, grant, and grant collection itself. Exact-project
  selectors are resolved through the existing ProjectRepository; request/path
  project IDs are never accepted as authority facts.
- Decisions add one bounded `resource_context_digest` over the complete typed
  resource context. Grant-backed decisions additionally add bounded
  `matched_grant_id` and `matched_scope_project_id` fields. Audit evidence
  records the exact matched grant and canonical project when applicable.
- Effective admin candidates are active grants whose role contains the exact
  permission, whose system/project scope covers the canonical resource, whose
  target is an active human ActorProfile with at least one active identity
  link, and whose request identity link remains active.
- Reads reload candidates per request. Under D28, mutations lock and revalidate
  the caller ActorProfile, exact caller identity link, and matched Access
  Administrator grant
  in the committing transaction. Replays reauthorize current authority before
  returning the stored response reference.
- Evaluation order is link lifecycle, actor lifecycle, registered/active
  action, candidate grant and scope, then canonical resource existence and
  guards. Unauthorized callers cannot distinguish absent from concealed actor,
  project, or grant selectors.
- Unknown, planned, wrong-resource, wrong-scope, inactive-grant, and
  unimplemented actions fail closed. Token roles never enter a candidate set.

## Shared dependency repair required before new consumers

AUTH-08 repairs three confirmed merged AUTH-07B regressions before adding admin
consumers:

- `get_authorization_service` never commits an arbitrary open shared-session
  transaction on successful teardown. Each protected route explicitly commits
  its own read-plus-decision or mutation-plus-decision unit. Dependency teardown
  rolls back any transaction a route left open, so a forgotten/deferred feature
  commit cannot be rescued by dependency ordering.
- The kernel/audit boundary catches `SQLAlchemyError` only around its own allow
  or deny evidence write and raises a typed `AuthorizationEvidenceUnavailable`.
  The authorization composition dependency catches only that typed exception,
  rolls back, and maps it once to the existing retryable 503
  `service_unavailable` envelope. Feature persistence errors remain owned by
  feature routes and cannot be relabeled as evidence failures.
- For an existing actor, successful protected GET/PATCH access advances both
  `ActorProfile.last_seen_at` and `ActorIdentityLink.last_verified_at` once in
  the route-owned transaction after authorization. D28 supersedes this
  contract's original lock-order clause: current helpers lock ActorProfile then
  the exact ActorIdentityLink and use execution-time
  `GREATEST(current_value, clock_timestamp())`, never transaction-start
  `now()`. Kernel denial or evidence/business persistence failure rolls both
  back. First-access provisioning retains its existing atomic actor/link
  creation behavior. Repeated and independent-session crossed-commit API tests
  prove monotonic database-time advancement and unchanged timestamps after
  denied/failed requests.

## AuthorityControl, bootstrap, and lock order

Migration `0022` creates and seeds exactly one `AuthorityControl(id=1)` row with
`bootstrap_completed=false`, `bootstrap_grant_id=NULL`, and `version=0`.
Runtime cannot insert, delete, reset, or replace it. Execution atomically moves
it once to `bootstrap_completed=true`, the created grant ID, and `version=1`.
Current grant state never reopens bootstrap.

An effective Access Administrator is exactly an active, system-scoped
`access_administrator` grant targeting an active human profile with at least
one active identity link. Bootstrap target eligibility uses the same actor and
identity-link facts.

All bootstrap and admin grant mutations intentionally serialize in this order:

```text
idempotency reservation when HTTP
-> AuthorityControl(id=1) FOR UPDATE
-> exact caller ActorProfile then exact caller identity link when HTTP
-> exact matched Access Administrator grant when HTTP
-> target grant, target ActorProfile then exact target identity-link selector,
   then project row
-> state, evidence, invalidation, and idempotency completion
-> one route/command-owned commit
```

The shared lock is acquired even for non-Access-Administrator grant mutations
to preserve one global order. AUTH-09 must reuse this control-first order for
profile suspension/deactivation and identity-link revocation; those mutations
are not implemented here.

The local command is:

```text
python -m scripts.bootstrap_access_administrator \
  --actor-profile-id <uuid> (--dry-run | --execute)
```

`--dry-run` performs bounded read-only eligibility checks, never locks in a
promise, never changes state, and outputs only JSON containing `result_code`,
`actor_profile_id`, and `would_change`. `--execute` is the only state-changing
mode and outputs `result_code`, `actor_profile_id`, `grant_id`, and `changed`.
No issuer, subject, email, display name, token, or reason text is emitted.
Exit codes are 0 success/eligible dry-run, 2 invalid or ineligible target, 3
already bootstrapped/concurrent loser, and 1 infrastructure failure.

Execution locks AuthorityControl first, validates the target, creates one
system Access Administrator grant attributed to
`workstream:system:bootstrap`, marks the irreversible control state, writes
`InitialAccessAdministratorBootstrapped`, and commits once. Later and losing
attempts use stable `admin_role_grant_exists`, roll back the losing transaction,
then commit one `AdminRoleGrantIssueDenied` event in a clean transaction before
exit 3. Bootstrap is never an idempotent replay and has no HTTP route or secret.

## AdminRoleGrant persistence and migration

`AdminRoleGrant` stores a UUID ID, target actor ID, role, scope type, optional
project FK, status, version, creation attribution, bounded reasons, database-time
timestamps, and complete optional revocation attribution. The business row
persists the bounded operator-readable `grant_reason` and `revoked_reason`;
only `AuthorityIdempotencyRecord` stores their canonical request digest, while
audit stores its closed reason classification. Normal grants require both
`granted_by_actor_profile_id` and the FK-backed
`granted_by_admin_role_grant_id` that the kernel matched. Bootstrap alone uses
the mutually exclusive fixed system-principal attribution with both human
grantor fields null. Revocation records the acting human, the exact
`revoked_by_admin_role_grant_id`, bounded reason, and database time.

Database enforcement includes:

- actor and grantor existence FKs, authorizing-grant FKs, and project FK when
  project-scoped; a PostgreSQL insert trigger rejects a non-human target while
  runtime locked queries enforce active-profile/active-link eligibility;
- role/scope compatibility and attribution XOR constraints;
- one active system grant per `(target_actor_id, role)` and one active project
  grant per `(target_actor_id, role, scope_project_id)` through separate partial
  unique indexes;
- immutable identity, target, role, scope, creator, reason, and creation fields;
- only one legal `active/version=1` to `revoked/version=2` transition with all
  revocation actor, authorizing grant, reason, and time fields set together;
- triggers rejecting delete, truncate, reset of AuthorityControl, later grant
  updates, or incomplete revocation;
- indexes for effective-candidate, target-history, project-scope, and final
  Access Administrator queries.

Direct-SQL tests prove a service target is rejected, normal issuance cannot
omit either human/authorizing-grant provenance, bootstrap cannot carry human
provenance, and every immutable reason/provenance field survives revocation.

Upgrade from `0021` fails closed if orphan bootstrap/admin-grant success history
or admin-grant idempotency history already exists without canonical grant rows.
Clean downgrade is allowed only while bootstrap remains incomplete and no
AdminRoleGrant, AUTH-08 action evidence, AUTH-08 domain evidence, or admin-grant
idempotency row exists. Otherwise recovery proceeds forward.

## API request, response, privacy, and replay contract

- Permission definitions return exactly
  `{"items":[{"permission_id": <PermissionId>}],"total":74}` with items sorted
  lexicographically by PermissionId. Administrative role definitions return
  exactly `{"items":[{"role": <AdminRole>,"allowed_scopes": [...],
  "permission_ids": [...]}],"total":5}` in AdminRole declaration order, with
  allowed scopes and permission IDs in their declared immutable order. No
  action availability, grant state, description, or dynamic policy body is
  exposed by either definition endpoint.
- A grant-history item contains exactly `grant_id`, `target_actor_profile_id`,
  `role`, `scope_type`, `scope_project_id`, `status`, `version`,
  `granted_by_ref_kind`, `granted_by_ref`,
  `granted_by_admin_role_grant_id`, `grant_reason`, `granted_at`,
  `revoked_by_actor_profile_id`, `revoked_by_admin_role_grant_id`,
  `revoked_reason`, and `revoked_at`. Nullable revocation fields remain null for
  active grants. Collection envelopes contain exactly `items`, `total`, and
  `next_cursor`, ordered by `(granted_at, grant_id)` ascending.
- Both mutation routes require a UUID `Idempotency-Key` header and a human
  reason of 1-500 UTF-8 bytes; the business row preserves the bounded reason,
  while idempotency preserves only its canonical request digest.
- Issue accepts target actor ID, role, scope type, and optional project ID.
  Revoke accepts only the path grant ID plus reason.
- Mutation responses are the stable bounded authority response reference:
  `resource_type`, `resource_id`, `version`, and original HTTP status. Issue is
  201/version 1; revoke is 200/version 2. Exact replay returns that same
  reference even if a later operation changed current grant state.
- Same key/digest reauthorizes and replays. Same key/different digest returns
  `idempotency_mismatch`. A different key for an already-active identical grant
  returns `admin_role_grant_exists`. Revoking an already-revoked grant with a
  new key returns concealed `grant_not_found`. Revoke authorization treats an
  existing same-key replay or mismatch record as sufficient to conceal current
  grant inactivity until the stored idempotency outcome is classified.
- Exact public statuses are 403 `self_grant_forbidden`, 403
  `self_role_revoke_forbidden`, 404 `grant_not_found`, 409
  `last_access_administrator`, 409 `admin_role_grant_exists`, and 409
  `idempotency_mismatch`. All remaining selector/target outcomes are closed:

  | Condition | HTTP/code |
  |---|---|
  | malformed Pydantic body/query fields, including status, limit, UUID, or enum | 422 `invalid_request` |
  | malformed opaque cursor or domain-parsed incompatible list scope/project combination | 400 `invalid_request` |
  | role incompatible with a structurally valid system/project scope | 422 `invalid_role_scope` |
  | caller has no candidate permission | 403 `permission_not_granted` |
  | caller's effective grant does not cover the selected project scope | 403 `scope_not_authorized` |
  | authorized issue target actor is absent, non-human, inactive, or has no active identity link | 404 `actor_not_found` |
  | authorized selected grant is absent or inactive | 404 `grant_not_found` |
  | authorized canonical project is absent | 404 `resource_not_found` |

  Authority and scope evaluation precede target existence, so unauthorized
  callers never learn which target condition occurred. Table-driven API tests
  cover every row, invalid list-scope combinations, and identical concealment
  envelopes.
- POST routes reuse the independently committed durable `admin_mutation` rate
  control before the product-authority unit of work. Authenticated GET routes
  consume no dedicated rate-control bucket in AUTH-08 and are not idempotent
  operations.
- Grant collection reads require `scope_type=system` with no project ID or
  `scope_type=project` with one canonical project ID. They accept status
  `active|revoked|all`, limit 1-100 (default 50), and an opaque
  `(created_at,id)` cursor. Results order by creation time then ID. Actor history
  uses the same required scope selector. Authorization filtering occurs before
  items, total, and next cursor are calculated.
- Responses contain only grant ID, target actor ID, role, scope, status,
  version, grantor/revoker reference kind and bounded reference, the exact
  authorizing grant references, operator-readable bounded reasons, and database
  timestamps. They never include issuer, subject, token claims, email, display
  name, or project details.
- `/api/v1/actors/me` projects `admin_roles` as sorted unique active role tokens
  covering that actor and keeps `project_role_grants` unchanged. This is a
  self-visible informational projection with no scope claims and is never an
  authority candidate; the scoped history APIs are authoritative.

## Atomic mutation and denial evidence

HTTP issue/revoke follows one caller-session sequence: reserve first, lock
AuthorityControl, call the central kernel (which revalidates caller/grant and
canonicalizes the target selector), mutate, write success and invalidation,
complete idempotency, then commit once. Reservation outcomes are not exposed
until current authorization succeeds. Mutation success, invalidation,
idempotency-mismatch, and post-allow conflict evidence derives request and
correlation IDs only from that exact authorization decision; the feature
service accepts no alternate identifiers from callers.

Issue invalidates the target actor authority projection from
`effective=false` to `effective=true`; revoke invalidates that same target
actor projection from `effective=true` to `effective=false`. The invalidation
targets the actor profile, not a newly issued grant. `AuthorityMutationService`
must verify the direction and target from the exact operation/request/success
facts. This AUTH-08 decision explicitly corrects AUTH-05B's generic
grant-resource `true -> false` placeholder for these two operations; migration
`0022`, typed audit validation, PostgreSQL constraints, and tests admit exactly
these actor-projection directions. Success, invalidation, state, and
idempotency completion are atomic.

Denial orchestration has three separate paths:

- a kernel or resource-guard denial rolls back, then restages only that exact
  pending central decision; self-grant and self-revoke are central denials using
  `self_grant_forbidden` and `self_role_revoke_forbidden`;
- an idempotency mismatch rolls back any staged allow and extends the AUTH-05B
  mismatch context/service to validate and persist the exact registered
  `admin_role_grant.issue` or `admin_role_grant.revoke` ActionId with its mapped
  permission; typed and PostgreSQL tests reject missing/wrong pairs; and
- a post-allow business conflict rolls back the staged allow and state, then
  commits only its registered domain event in a clean transaction.

Duplicate issue and bootstrap conflict use `AdminRoleGrantIssueDenied`.
Final-administrator revoke uses `LastAccessAdministratorOperationDenied`.
Inactive/concealed revoke uses the central `grant_not_found` denial and no
invented revoke-domain event. No allowed decision is transformed into or
restaged as a denial.

## Acceptance criteria

- All exact action, role-matrix, runtime, bootstrap, persistence, API,
  transaction, privacy, and evidence rules above are implemented.
- Permission and admin-role definition endpoints return the exact immutable
  registered data and no runtime grant state.
- Only an effective system Access Administrator issues or revokes grants; Audit
  Authority remains read-only and scope-filtered.
- Bootstrap succeeds exactly once for an existing authenticatable active human
  and records one grant/control transition/success event atomically.
- No public bootstrap route, secret, SQL instruction, or alternate policy
  service exists.
- Same-key issue/revoke replay commits no duplicate mutation, success, or
  invalidation evidence and still reauthorizes current authority.
- PostgreSQL independent-session barrier tests without sleeps prove: different-
  target bootstrap yields one success and one committed conflict; same-key
  issue yields one commit plus replay; different-key duplicate issue yields one
  grant plus one conflict; two administrators concurrently revoking each other
  leave at least one authenticatable effective Access Administrator; revoke
  versus authorization is proved by administrator A issuing a Project Manager
  grant while administrator B revokes A's matched Access Administrator grant.
  If issue locks first, one issue and one revoke succeed with one success and
  invalidation pair each. If revoke locks first, revoke succeeds and issue
  revalidation commits one central denial with no issued grant or issue success
  evidence. No third outcome or duplicate evidence is permitted.
- Migration tests prove direct-SQL constraints/triggers, prior-head
  `0021 -> 0022 -> 0021 -> 0022` on an empty forward state, non-empty downgrade
  refusal, immutable revoked history, and preserved attribution.
- Real signed issuer-token API tests use the canonical actor/authorization
  dependencies with no dependency overrides, token-role authority, or direct
  grant inserts as product proof. The supported bootstrap command is used to
  establish the first administrator.
- OpenAPI and command manifest tests prove every introduced surface has exactly
  one active action and no bootstrap HTTP route exists.
- Shared-dependency regression tests prove explicit route commit ownership,
  rollback of forgotten commits, stable retryable evidence-failure 503s, no
  partial state, and the exact successful/denied/failed verification-timestamp
  semantics before any new admin route is treated as consumable.
- GET/PATCH/issue/revoke commit-failure tests prove rollback, retryable 503
  `service_unavailable`, zero partial decision/domain/idempotency/business/
  timestamp state, and a subsequent successful retry whose timestamps advance
  exactly once.
- Materially changed authorization, dependency, and route behavior remains at
  or above 90 percent branch-aware focused coverage. Global CI preserves the
  repository-wide 78 percent floor. No test is skipped, weakened, or excluded.
- Runbook assigns bootstrap custody, environment access, dry-run/evidence,
  retry/failure handling, rollback responsibility, and post-bootstrap
  verification.

## Verification commands

```bash
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-db> \
  .venv/bin/python -m pytest -q tests/test_isolated_database_runner.py)
(metadata_dir="$(mktemp -d)"; trap 'rm -rf "$metadata_dir"' EXIT; \
  cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-db> \
  .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "$metadata_dir/alembic.json" --timeout-seconds 1800 -- \
  .venv/bin/python -m pytest -q tests/test_alembic.py)
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(metadata_dir="$(mktemp -d)"; trap 'rm -rf "$metadata_dir"' EXIT; \
  cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-db> \
  .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "$metadata_dir/focused.json" --timeout-seconds 3600 -- \
  .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_audit.py \
  tests/test_auth.py tests/test_actors.py tests/test_api_controls.py \
  tests/test_api_rate_controls.py tests/test_projects.py tests/test_app.py \
  --cov=app.modules.authorization --cov=app.api.deps.authorization \
  --cov=app.modules.actors.repository --cov=app.modules.actors.service \
  --cov=app.modules.actors.schemas --cov=app.modules.audit.schemas \
  --cov=scripts.bootstrap_access_administrator \
  --cov-branch --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)"; trap 'rm -rf "$metadata_dir"' EXIT; \
  cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-db> \
  .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "$metadata_dir/full.json" --timeout-seconds 12600 -- \
  .venv/bin/python -m pytest -q \
  --ignore=tests/test_isolated_database_runner.py --cov=app \
  --cov-report=term-missing --cov-fail-under=78)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<isolated-test-db> \
  WORKSTREAM_DATABASE_URL=<isolated-test-db> \
  .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
git diff --check
```

GitHub Backend remains authoritative for the full suite and repository-wide 78
percent floor.

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Review bootstrap exposure, exact role/permission sets, action activation,
scope-filtered disclosure, idempotency/replay authorization, invalidation
direction, database immutability, the global lock order, and final Access
Administrator concurrency safety.

## Stop conditions

Stop if bootstrap requires SQL edits or a public secret; token roles become
authority; a project selector is trusted without canonical resolution; final-
administrator safety uses an unlocked count; replay skips current
authorization; grant history must be deleted; or tests/CI must be weakened.
