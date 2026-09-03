# Chunk Contract: WS-AUTH-001-09B - Controlled Service Actor Provisioning

## Goal

Activate only `actor.service.provision` and let an effective system Access
Administrator bind one opaque Identity Issuer subject to one unprovisioned
fixed service ActorProfile whose future authority remains derived from the
closed static matrix.

## Why this chunk exists

AUTH-09A established stable fixed identities and inert matrix candidates but
created no supported binding path. This chunk lets one already-authorized human
administrator bind the configured Identity Issuer to one fixed local service
principal. Provisioning records identity; it neither verifies a service token
nor admits that principal to runtime authorization.

## Allowed files

```text
backend/app/interfaces/auth.py
backend/app/core/auth.py
backend/app/adapters/auth/dev.py
backend/app/adapters/auth/flow.py
backend/app/modules/actors/**
backend/app/modules/authorization/**
backend/app/api/router.py
backend/app/api/deps/auth.py
backend/app/api/deps/authorization.py
backend/alembic/versions/0024_*.py
backend/tests/test_actors.py
backend/tests/test_audit.py
backend/tests/test_auth.py
backend/tests/test_config.py
backend/tests/test_authorization.py
backend/tests/test_alembic.py
backend/tests/test_tasks.py
backend/tests/test_api_controls.py
backend/tests/test_api_rate_controls.py
backend/tests/test_api_contract_e2e.py
backend/scripts/api_contract_e2e.py
scripts/test_agent_gates.py
.github/workflows/backend.yml
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-09B.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
client-supplied issuer, ActionIds, PermissionIds, roles, grants, or assignments
generic or unknown service identities
service actor list/detail routes
broadening the human admin dependency to admit service callers
artifact action activation, resource composition, or adapter attachment
editing historical migrations
compatibility aliases, fallback constructors, provider-name branches, dual
issuer paths, a second external-identity lock helper, or a second service
identity model
```

## Exact surface

| Route | ActionId | PermissionId | Canonical target | Candidate |
|---|---|---|---|---|
| `POST /api/v1/service-actors` | `actor.service.provision` | `actor.service.provision` | requested unprovisioned fixed service identity | effective system-scoped Access Administrator grant |

The strict body contains only `service_identity`, opaque `subject`, and required
`reason`. `service_identity` is the closed `ServiceIdentity` enum. `subject` is
one non-empty identity anchor of at most 200 UTF-8 bytes with no leading or
trailing whitespace. Accepted subjects are preserved byte-for-byte and are
never normalized, logged, returned, or placed in evidence.
`reason` is bounded to 1-500 UTF-8 bytes, is never persisted, and only its
canonical digest enters idempotency input. The required `Idempotency-Key` is a
UUID.

The issuer comes only from `AuthVerifier.canonical_issuer()`. The verifier port
returns the exact validated configured issuer; development and Flow adapters
return that exact `_issuer`, and the unavailable verifier fails closed. Adapter
tests prove `canonical_issuer()` exactly equals the issuer used by a successful
token result for that verifier.
The route injects the existing application verifier and never selects a
provider, reads a caller identity link as issuer configuration, or accepts an
issuer override. The identity digest binds this issuer and the byte-exact
subject. Its helper accepts the exact already-validated configured issuer under
the same non-empty bounded identity-anchor rules; it does not impose an
`https://` scheme, renormalize the issuer, or branch by provider.

The canonical `ServiceActorCreateRequest` contains only the operation, fixed
`service_identity`, `identity_reference_digest`, and `reason_digest`. Its full
canonical hash therefore binds operation, service identity, issuer/subject, and
reason. The generated actor UUID is excluded. The obsolete
`profile_payload_digest` field and `derive_service_profile_digest` helper are
removed without aliases or translation.

Authorization uses a frozen `ServiceActorProvisionResourceContext` with exactly
`resource_type: Literal["service_actor_provisioning"]` and
`resource_id: ServiceIdentity`. The resource type and ID are included in the
closed authorization context/decision unions and kernel admin-action matching.
An occupied identity is a domain conflict only after an allowed decision; the
kernel must not convert it into an authorization denial.

A new service ActorProfile receives a random UUID independent of issuer or
subject; the fixed `service_identity` is its stable local name. `created_by` and
`linked_by` are the authorized human ActorProfile ID. The response contains only
`actor_profile_id`, `service_identity`, fixed active actor/link statuses,
`manual_service_provisioning`, `created_at`, and `linked_at`. It returns no link
ID, subject, issuer, email, raw reason, grant, token material, or assignment.

## Transaction, lock, and concurrency contract

The caller-owned transaction has one canonical order:

1. reserve caller/operation/idempotency namespace;
2. lock `AuthorityControl(id=1)`;
3. lock the human caller `ActorProfile`;
4. lock the caller's exact `ActorIdentityLink`;
5. lock the exact matched active system Access Administrator grant;
6. acquire one advisory lock for the fixed `service_identity`;
7. use `ActorRepository.lock_external_identity()` for the exact configured
   issuer and subject;
8. check service-identity occupancy first, then issuer/subject occupancy;
9. stage actor, link, decision/success/invalidation evidence, and idempotency
   completion; and
10. flush participants and commit once in the route.

The fixed-identity advisory key is a separate domain from the external-identity
key. No second external-identity helper exists. Current canonical human lock
helpers are repaired within this chunk where needed so they all follow profile
then exact link, including `AdminAuthorizationRepository.lock_request_actor`,
`lock_eligible_human`, `ActorService.lock_actor_self_for_authorization`, and
`ActorRepository.touch_verified_actor`. No 09B path may consume the old inverse
link/profile order.

Independent-session barrier tests cover same key/same request, same key/different
request, different keys/same service identity/different subjects, different
service identities/same issuer and subject, same pair/different keys,
rollback/retry, and crossed caller profile/link/grant revocation or lifecycle
mutation. They assert no deadlock; one actor/link at most; one completed
idempotency success/invalidation pair; and no pending, partial, or duplicate
evidence.

Conflict precedence is deterministic: occupied fixed service identity first,
then occupied exact issuer/subject. Public 409 codes are
`service_identity_already_provisioned` and `identity_subject_already_linked`.
After rolling back staged mutation state, conflict evidence is one
`SensitiveAuthorizationDenied` using the existing closed
`identity_link_conflict` denial code, the action, permission, and matched grant;
it includes no issuer, subject, raw reason, or raw resource value. Same-key drift
is `idempotency_mismatch`. SQL, decision-evidence, success-evidence,
invalidation-evidence, or commit failure rolls back and maps to the retryable
`service_unavailable` 503 envelope.

## Evidence contract

`SensitiveAuthorizationAllowed` is the decision event and carries
`actor.service.provision`, `actor.service.provision`, and the matched grant.
`ServiceActorProvisioned` is the mutation success event; it carries the created
profile, exact idempotency record, request/correlation IDs, permission, request
digests, and fixed lifecycle facts, but no ActionId. The linked
`AuthorityInvalidationRequested` references that success cause plus the same
idempotency/request/correlation chain and does not duplicate the matched grant.

The existing validation direction remains `effective=true -> false`. For this
operation it invalidates any cached negative identity-absence or actor lookup
projection after the local binding changes; it does not claim the service had,
gained, or lost executable authority. `_EVIDENCE[service_actor.create]` becomes
action-aware so mismatch and conflict denials carry the exact action. Completion
validates request digests, decision/resource equality, created-profile response,
success event, invalidation cause, and the shared idempotency chain. No separate
identity-linked success event is added.

## Verification timestamp contract

Provisioning is not service-token verification. Migration `0024` removes the
identity-link timestamp default, makes `last_verified_at` nullable only for
service links, and adds a current constraint requiring every human link to have
a timestamp. Human first access explicitly writes database time. A newly
provisioned service ActorProfile has `last_seen_at = null`; its link has
`last_verified_at = null`. AUTH-09E alone may advance them after successful
verification of that exact service token.

The exact state table is:

| Outcome | Human caller profile/link | Service profile/link |
|---|---|---|
| successful create | both advance in the committed transaction | creation fields remain immutable; `last_seen_at` and `last_verified_at` remain null |
| successful replay | both advance after current authority revalidation | no field advances |
| mismatch, denial, conflict, SQL/evidence/commit failure | neither advances | no row or timestamp change |

The migration downgrade first refuses while any service link has a null
verification timestamp, then restores non-null/default semantics. Historical
migrations remain immutable. ART owns `0025` for the ArtifactStore v2 clean
cut. AUTH-10 through AUTH-15 move to `0026` through `0031` respectively.

## Acceptance criteria

- Exactly one action becomes active: totals are 65 actions, 10 active and 55
  planned. One generated manifest declaration exists for the route.
- Provisioning atomically creates one active fixed service ActorProfile and one
  active exact issuer/subject link plus the exact evidence/idempotency chain. It
  creates no assignment or grant rows and grants no executable service action.
- Replay revalidates current human authority, rejects a deactivated service
  profile or revoked service link, reconstructs the original response from
  immutable active creation facts, advances only caller verification
  timestamps, and never touches service verification state.
- Canonical request drift is independently proved for service identity,
  issuer/subject digest, and reason digest.
- Unknown identities, service callers, agent/space subjects, duplicate subjects,
  SQL/evidence/commit failures, and unavailable persistence leave no partial
  actor/link/idempotency/evidence/timestamp state.
- Invalid body, header, conflict, denial, response, log, and audit tests prove
  opaque subject, configured issuer, token, email, and raw reason never escape;
  422 validation output must not echo rejected subject or reason input.
- The admin mutation limiter applies. The route owns its one commit and
  dependency teardown never commits shared-session state.
- Only AUTH-09E may admit fixed services. This chunk does not weaken
  `get_authorization_actor`, evaluate a human grant for a service caller, or
  activate any ART, REV, or CON action. Both `get_authorization_actor` and the
  legacy `get_canonical_actor` dependency deny every service subject before any
  actor lookup, canonical resolution, or timestamp touch. Representative central
  AUTH and legacy-route tests present a provisioned service token and prove the
  same stable denial while service `last_seen_at` and `last_verified_at` remain
  null. AUTH-09E alone may remove this pre-resolution denial.
- Focused actor and authorization subsystem branch coverage is each at least 90
  percent; GitHub Backend preserves the repository-wide 78 percent floor.

## Migration and compatibility boundary

Migration `0024` owns only service-link verification timestamp semantics and
current constraints. Migration `0023` remains the immutable fixed-identity
foundation; `0021`/`0022` remain immutable audit history. Typed current-code
validators change only where the exact 09B contract requires. No old request
shape, helper, route, alias, inferred identity, token-role authority, provider
fallback, or dual issuer path is retained or introduced.

## Risk and reviewers

L1 / P1. Required: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts/api_contract_e2e.py)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q \
  tests/test_actors.py tests/test_auth.py tests/test_authorization.py \
  tests/test_alembic.py tests/test_config.py tests/test_api_controls.py \
  tests/test_api_rate_controls.py)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m coverage erase)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m coverage run \
  --branch --source=app.modules.actors -m pytest -q tests/test_actors.py \
  tests/test_auth.py tests/test_authorization.py tests/test_actor_legacy_classification.py \
  tests/test_actor_migration_tools.py)
(cd backend && .venv/bin/python -m coverage report --fail-under=90)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m coverage erase)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m coverage run \
  --branch --source=app.modules.authorization -m pytest -q \
  tests/test_authorization.py tests/test_actors.py tests/test_auth.py \
  tests/test_api_controls.py tests/test_api_rate_controls.py)
(cd backend && .venv/bin/python -m coverage report --fail-under=90)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m coverage erase)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m coverage run \
  --branch --source=app.interfaces.auth,app.core.auth,app.adapters.auth.dev,app.adapters.auth.flow \
  -m pytest -q tests/test_auth.py tests/test_config.py)
(cd backend && .venv/bin/python -m coverage report --fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && \
  cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-db> \
  .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "$metadata_dir/result.json" --timeout-seconds 3600 -- \
  .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Human review focus

Review the server-owned issuer port, exact fixed identity, nullable unverified
service timestamp, profile-before-link locks, opaque request/evidence chain,
atomic idempotent creation, no grants, and continued service-action denial.

## Stop condition

Stop after merge and signed memory. Do not start AUTH-09C automatically.
