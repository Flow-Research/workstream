# Chunk Contract: WS-AUTH-001-05B - Authority Idempotency And Invalidation Foundation

## Status

Active on `codex/ws-auth-001-05b-idempotency-invalidation`. AUTH-05A, catalogue
reconciliation, and their post-merge memory checkpoints are merged. The user's
AUTH-05B start signal is recorded. The repaired L1 preimplementation plan passed
senior engineering, QA/test, and security/auth/privacy review.

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Add concurrency-safe authority-mutation reservation/replay and typed success,
denial, and invalidation orchestration on the shared AUTH-05A audit envelope.

## Risk and circuit breaker

- Risk: L1 / SLA P1.
- The circuit breaker is this contract's semantic boundary, typed/SQL parity,
  acceptance evidence, and reviewability rather than a production-line count.
- Stop and replan if the boundary expands; do not compress or split an atomic
  database/runtime invariant to satisfy a numeric ceiling.

## Allowed files

```text
backend/app/modules/authorization/**
backend/app/db/models.py
backend/alembic/versions/0019_authority_idempotency.py
backend/tests/test_authorization.py
backend/tests/test_audit.py
backend/tests/test_alembic.py
docs/architecture_data_model.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
routes, dependencies, middleware, or generic unit-of-work wrappers
actor/profile migration or first-access behavior
permissions, grant tables/APIs, or product authorization cutover
invalidation consumers, caches, queues, or external delivery
token-role or IdentityIssuerVerifier/factory changes
raw request/response bodies, URLs, PII, secrets, or arbitrary JSON persistence
workflow, dependency, threshold, skip, or exclusion changes
repository/service commit, rollback, or parallel session creation
```

## Idempotency schema and namespace

Migration `0019_authority_idempotency` uses exact
`down_revision = "0018_authority_audit_evidence"` and creates
`authority_idempotency_records`. Each record contains:

- UUID primary key and canonical UUID idempotency key;
- actor reference kind plus stable opaque actor reference;
- closed operation token;
- canonical request digest using existing
  `app.core.hashing.canonical_json_hash` (`sha256:` plus 64 lowercase hex);
- status `pending` or `committed`;
- typed committed response reference: resource type, resource ID, optional
  version, and successful HTTP status; never a body, URL, or free-form JSON;
- database-owned created/committed timestamps.

The unique replay namespace is
`(actor_ref_kind, actor_ref, operation, idempotency_key)`. Different actors or
reference kinds may reuse a key without collision or visibility. Operation,
target project/resource, and mutation payload are included in the canonical
request object/digest. Request ID, correlation ID, and the idempotency key are
excluded from the digest so legitimate retries may carry new request context.
The raw request is never persisted.

The canonical request object is a typed, bounded JSON-compatible dictionary.
It uses the shared canonical hash helper; no authorization-local encoder is
introduced.

The closed idempotency operations are exactly:

```text
service_actor.create
admin_role_grant.issue
admin_role_grant.revoke
project_role_grant.issue
project_role_grant.revoke
actor_profile.suspend
actor_profile.reactivate
actor_profile.deactivate
actor_identity_link.revoke
actor_identity_link.reactivate
```

These are idempotency-operation tokens, not AUTH-07 `ActionId` values. Project
role issue targets one exact independent role and never replaces another role.
Bootstrap,
first-access provisioning, qualification capture, and identity-link creation
are not in this registry. Each operation has the exact `extra="forbid"` request
variant below. Unknown, extra, mistyped, overlong, non-canonical, or nested
free-form values fail before hashing. Actor kind/reference rules match AUTH-05A.

Every variant is frozen and scalar-only, revalidated into one immutable
snapshot, and serialized with `model_dump(mode="json", exclude_none=True)`
before hashing. Its canonical encoded object is limited to 2,048 bytes. Raw
issuer/subject, display data, human reason, request body, token, idempotency key,
request ID, and correlation ID are never persisted. Validation errors are
generic and retain or echo none of the rejected value.

`reason_digest`, `identity_reference_digest`, and `profile_payload_digest` are
internal server-derived strings matching exact `sha256:[0-9a-f]{64}` syntax.
They are produced with `canonical_json_hash` from frozen, strict, bounded
snapshots of the applicable human reason, verified normalized issuer/opaque
subject, and service profile payload. HTTP/request callers cannot supply these
digests. The identity snapshot comes only from verified issuer output; different
issuer/subject pairs cannot select one stored fingerprint through a request
field.

| Operation | Canonical request variant and exact fields | Permission | Audit reason | Response | Success event | Invalidation target |
|---|---|---|---|---|---|---|
| `service_actor.create` | `ServiceActorCreateRequest(operation, identity_reference_digest, profile_payload_digest)` | `actor.service.provision` | `manual_service_provisioning` | `actor_profile`, `201` | `ServiceActorProvisioned` | `actor_profile` |
| `admin_role_grant.issue` | `AdminRoleGrantIssueRequest(operation, target_actor_id, role, scope_type, scope_project_id?, reason_digest)` | `admin_role.grant` | `authority_assignment` | `admin_role_grant`, `201` | `AdminRoleGrantIssued` | `admin_role_grant` |
| `admin_role_grant.revoke` | `AdminRoleGrantRevokeRequest(operation, grant_id, reason_digest)` | `admin_role.revoke` | `authority_revocation` | `admin_role_grant`, `200` | `AdminRoleGrantRevoked` | `admin_role_grant` |
| `project_role_grant.issue` | `ProjectRoleGrantIssueRequest(operation, project_id, target_actor_id, role, reason_digest)` | `project.role_grant.manage` | `authority_assignment` | `project_role_grant`, `201` | `ProjectRoleGrantIssued` | `project_role_grant` |
| `project_role_grant.revoke` | `ProjectRoleGrantRevokeRequest(operation, project_id, grant_id, reason_digest)` | `project.role_grant.manage` | `authority_revocation` | `project_role_grant`, `200` | `ProjectRoleGrantRevoked` | `project_role_grant` |
| `actor_profile.suspend` | `ActorProfileSuspendRequest(operation, actor_profile_id, reason_digest)` | `actor.profile.suspend` | `security_response` or `administrative_correction` | `actor_profile`, `200` | `ActorProfileSuspended` | `actor_profile` |
| `actor_profile.reactivate` | `ActorProfileReactivateRequest(operation, actor_profile_id, reason_digest)` | `actor.profile.reactivate` | `administrative_correction` | `actor_profile`, `200` | `ActorProfileReactivated` | `actor_profile` |
| `actor_profile.deactivate` | `ActorProfileDeactivateRequest(operation, actor_profile_id, reason_digest)` | `actor.profile.deactivate` | `security_response` or `administrative_correction` | `actor_profile`, `200` | `ActorProfileDeactivated` | `actor_profile` |
| `actor_identity_link.revoke` | `ActorIdentityLinkRevokeRequest(operation, identity_link_id, reason_digest)` | `actor.identity_link.revoke` | `identity_lifecycle_change` | `actor_identity_link`, `200` | `ActorIdentityLinkRevoked` | `actor_identity_link` |
| `actor_identity_link.reactivate` | `ActorIdentityLinkReactivateRequest(operation, identity_link_id, reason_digest)` | `actor.identity_link.reactivate` | `identity_lifecycle_change` | `actor_identity_link`, `200` | `ActorIdentityLinkReactivated` | `actor_identity_link` |

Admin issue roles are exactly `access_administrator`, `operator`,
`project_manager`, `finance_authority`, or `audit_authority`.
`access_administrator` and `operator` require `system` scope with no project;
the other three admit `system` with no project or `project` with exactly one
project UUID. Project issue roles are exactly `submitter`, `reviewer`, or
`adjudicator`.
Create/issue variants use deterministic request facts or existing
parents in the digest; a newly generated response resource UUID is never part
of their request digest.

## State machine and transaction ownership

- Reservation runs before any business-state flush.
- Under PostgreSQL `READ COMMITTED`, reservation executes `INSERT ... ON
  CONFLICT DO NOTHING RETURNING id`. On conflict it performs a full-namespace
  `SELECT ... FOR UPDATE`; the unique-index wait resolves the winning
  transaction before the locked read. A missing row after conflict, `40001`, or
  deadlock fails closed and is not translated to replay/mismatch; the caller
  rolls back and may retry the whole transaction at its bounded application
  boundary. Repository/service code does not perform retries.
- A new reservation returns `claimed` with a `pending` row in the caller's
  transaction.
- Same namespace and digest after commit returns `replay` with the existing
  typed committed reference and does not append duplicate success/invalidation
  events.
- Same namespace with a different digest returns a stable `mismatch` outcome;
  caller-owned application orchestration records the required denial event in
  a clean transaction before surfacing `idempotency_mismatch`.
- Completion atomically changes only the caller's pending row to `committed`
  and writes its typed response reference.
- A deferred database constraint rejects commit while a record is still
  pending. Rollback/cancellation removes the reservation and all co-transaction
  business/audit/invalidation rows; retry may then claim normally. A pending
  row is never stolen, expired, or treated as success.
- Repository/service methods may insert, lock, flush, and return typed outcomes
  only. The injected caller session alone commits or rolls back; no parallel
  unit-of-work abstraction or session is introduced.
- Reservation returns a discriminated `claimed`, `replay`, or `mismatch`
  result. A claim is an opaque typed handle containing record ID, namespace,
  operation, and digest. Completion conditionally updates exactly one matching
  pending record; forged, stale, or wrong-namespace handles fail closed.
  Same-session re-entry while the caller's claim remains pending raises a
  stable internal pending error and is never replayed.
- Database enforcement owns both timestamps, permits only the
  `pending -> committed` transition, makes identity/namespace/digest immutable,
  makes committed response references immutable, and rejects update after
  commit, delete, or truncate. The deferred pending guard re-reads current row
  state so insert-pending/update-committed succeeds while durable pending state
  cannot commit.
- A replay reference is internal orchestration data. A later route-owning chunk
  must reload the canonical resource and reauthorize the current request before
  disclosing any resource identifier or representation.

## Invalidation and denial evidence

Invalidation is an `AuthorityInvalidationRequested` authority-domain
`AuditEvent`, not a second event table. Authorization constructs the narrow
typed invalidation input; `AuditService` and `AuditRepository` remain the sole
validation and persistence path. The event links its causing concrete domain
success event, exact operation-compatible target kind/reference,
request/correlation IDs, actor, reason, and claim record. AUTH-05B introduces
persistence and orchestration only: no cache, worker, adapter, or authority
behavior consumes the event.

Future owning domain services construct their concrete success event with the
merged AUTH-05A type. AUTH-05B validates it against the claim's actor,
request/correlation context, idempotency record, operation-to-permission,
operation-to-event, resource, and target before the shared writer persists it.
AUTH-05B does not create generic allowed decisions; AUTH-07 owns those.

`idempotency_reference` means the internal idempotency-record primary key, never
the client key. Migration `0019` adds a `NOT VALID` composite foreign key from
new audit references plus actor kind/reference to the matching idempotency
record's unique `(id, actor_ref_kind, actor_ref)` key, preserving any pre-0019
forward references while enforcing every new write. The 0019 audit trigger
requires every new mapped success and every new invalidation event to carry a
non-null idempotency reference. It enforces record operation to success-event,
permission, resource type, resource ID, and invalidation-target mapping. A new
invalidation must reference a cause event with that same record and actor. The
successful mutation event flushes first, its required invalidation flushes
second, and only then may completion mark the claim committed. Completion also
requires exactly that mapped event pair and response resource. A failure at any
step leaves caller rollback to remove the entire transaction.

Mismatch orchestration constructs only a privacy-bounded
`SensitiveAuthorizationDenied` / `idempotency_mismatch` input from strict
context and the operation-to-permission mapping. The mismatch result contains
no existing record, digest, response, or foreign namespace data. Reservation
must be the caller's first write. On mismatch the caller rolls back that unit of
work, opens a clean transaction on the same injected session, asks AUTH-05B to
append denial evidence, commits it, and only then translates the stable error.
Repository and service code never commit, roll back, or create a session.
Denials are not stored as successful replay results.

## Migration custody

- Upgrade preserves all AUTH-05A audit rows and creates no idempotency or
  invalidation evidence.
- Tests assert exact table columns, constraints, indexes, deferred trigger,
  defaults, invalid rows, and database time.
- Downgrade takes writer-blocking locks and refuses without mutation when any
  idempotency row exists. Under the new-write composite reference and
  committed-row deletion guard, that predicate also covers every 05B-linked
  audit/invalidation event. Legacy rows, ordinary AUTH-05A rows, pre-0019
  unmatched forward references, and pre-0019 invalidation rows remain intact
  and do not incorrectly block an otherwise compatible downgrade.
- Downgrade locks `authority_idempotency_records` and then `audit_events` in
  deterministic `ACCESS EXCLUSIVE` order, performs every refusal check before
  DDL, and remains transactional. A concurrent writer cannot enter between the
  emptiness check and schema removal.
- Privileged fixture cleanup permits `0019 -> 0018 -> 0019`; re-upgrade restores
  the pending-commit guard. Destructive tests restore `head` in `finally`.

## Acceptance criteria

- Independent-session exact concurrent retries produce one committed result,
  exactly one concrete success event, and exactly one invalidation event with
  correct cause, actor, claim, resource, and insertion order.
- Concurrent mismatched requests produce one winner and one privacy-safe
  mismatch outcome; different actors/kinds remain isolated.
- Injected failure after reservation, synthetic business flush, audit insert,
  invalidation insert, completion, and commit attempt leaves either the complete
  transaction or nothing. Repositories never commit/rollback.
- Retry after rollback claims normally; commit of unfinished pending state
  fails closed and leaves no durable pending row after caller rollback.
- Exact replay adds zero business, success, invalidation, or denial rows.
- Mismatch adds exactly one denial and zero success/invalidation rows after the
  reservation transaction is rolled back.
- Committed records cannot be changed or removed; wrong, stale, or forged claim
  handles and same-session pending re-entry fail closed.
- Strict canonical request variants, response references, result variants, and
  PostgreSQL registries have exact parity. Response references admit only the
  operation-compatible resource type, canonical UUID, optional positive
  version, and the exact `200` or `201` status in the operation table.
- Mismatch denial evidence is created only after the reservation transaction is
  rolled back and contains no request body, digest, existing response, or
  conflicting namespace information.
- Concurrency tests use explicit process/task barriers and observed database
  lock state rather than timing sleeps. Commit-attempt rollback is proved with
  the real deferred database constraint, not a mocked session method.
- Direct SQL proves initial committed insertion fails, only pending-to-committed
  succeeds, mapped events reject null/nonexistent/cross-actor/mismatched-cause
  references, `convalidated` remains false, and an orphan seeded at 0018
  survives upgrade. The existing audit writer test creates a real 0019 record
  for new linked evidence rather than relying on an unmatched future UUID.
- Authorization tests submit hostile and state-changing `Mapping` inputs,
  mutate source values after validation, exceed the canonical-object limit, and
  use noncanonical UUID/digest forms. Secret-bearing rejected values must be
  absent from Pydantic `errors()`, `json()`, string, exception args, cause,
  context, and public state; the immutable snapshot and resulting digest remain
  unchanged after source mutation.
- No route, permission, grant, actor, product authority behavior, or
  invalidation consumer exists.

## Verification

```bash
cd backend
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
.venv/bin/python -m ruff check app tests
.venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "$tmp_dir/05b.json" --timeout-seconds 1800 -- \
  .venv/bin/python -m pytest -q \
  tests/test_alembic.py::test_authority_idempotency_schema_preserves_audit_and_guards_downgrade \
  tests/test_authorization.py tests/test_audit.py
.venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "$tmp_dir/05b-coverage.json" --timeout-seconds 1800 -- \
  .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_audit.py \
  --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90
.venv/bin/python -m pytest -q tests/test_isolated_database_runner.py
.venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "$tmp_dir/05b-full.json" --timeout-seconds 10800 -- \
  .venv/bin/python -m pytest -q tests \
  --ignore=tests/test_isolated_database_runner.py \
  --cov=app --cov-report=term-missing \
  --cov-fail-under=78
.venv/bin/docstr-coverage --config .docstr.yaml
cd ..
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_internal_review_evidence.py
git diff --check
```

Run the exact migration node before audit/authorization tests on the same
isolated database. Test delta must be additive and all CI integrity controls
remain unchanged.

## Required reviewers

- senior engineering
- QA/test
- security/auth and privacy
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Review replay namespace, canonical hashing, pending-commit prevention,
concurrency/rollback behavior, typed result privacy, invalidation causation,
committed-row immutability, clean mismatch evidence, claim-handle ownership,
and caller-owned transaction boundaries.

## Stop conditions

Stop if exact concurrency cannot serialize without a committed pending row,
denial evidence requires committing unrelated work, a route/grant/permission
must be introduced, or tests/CI must be weakened. AUTH-05B consumes the merged
05A audit envelope and sole-writer contract without reopening its registries,
typed writer, append-only rules, or migration. A missing audit primitive
requires stop and replan rather than reopening 05A custody. The narrow
0019-owned composite audit-reference constraint and linked-invalidation trigger
are the only allowed additions to the merged audit table; 0018 and the shared
audit schema/service/repository remain unchanged.
