# Chunk Contract: WS-AUTH-001-09C - Actor And Identity-Link Administration Reads

## Goal

Activate only `actor.profile.read` and `actor.identity_link.read` so an
authorized human administrator can inspect one exact canonical ActorProfile or
that actor's single v0.1 ActorIdentityLink without exposing external identity,
contact, lifecycle-reason, grant, or static service-authority data.

## Why this chunk exists

AUTH-09B made controlled service identities provisionable, while actor and
identity-link lifecycle administration remains intentionally unavailable until
AUTH-09D. Operators need bounded, individually addressed reads before they can
safely select a lifecycle target. This chunk provides those reads without list,
search, mutation, service-token admission, or project-scoped authority.

## Allowed files

```text
backend/app/modules/actors/**
backend/app/modules/authorization/**
backend/app/api/router.py
backend/app/api/deps/authorization.py
backend/tests/test_actors.py
backend/tests/test_auth.py
backend/tests/test_authorization.py
backend/tests/test_audit.py
backend/tests/test_api_controls.py
backend/tests/test_api_contract_e2e.py
backend/scripts/api_contract_e2e.py
scripts/test_agent_gates.py (only the authored lifecycle assertions that record
AUTH-09B merged and AUTH-09C active)
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-09C.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
actor or identity-link mutation
collection, list, search, total, or cursor-pagination endpoints
issuer, subject, contact email, raw reason, token, claim, grant, assignment,
created-by, lifecycle-actor, or static service-action-matrix disclosure
project-scoped authority for actor-registry reads
service-token admission
schema migration or new persistence table
artifact, task, review, project, or grant behavior
compatibility alias, fallback route, dual response shape, or legacy authority
removal, relaxation, runtime derivation, skipping, or reordering of any agent
gate, threshold, dependency pin, evidence, scanner, CI, or unrelated assertion
```

## Exact surfaces and authority

| Route | ActionId | PermissionId | Exact target | Candidate |
|---|---|---|---|---|
| `GET /api/v1/actors/{actor_profile_id}` | `actor.profile.read` | `actor.profile.read_any` | requested ActorProfile UUID | effective system-scoped Access Administrator or Audit Authority grant |
| `GET /api/v1/actors/{actor_profile_id}/identity-links` | `actor.identity_link.read` | `actor.identity_link.read` | requested actor UUID and its one v0.1 link | effective system-scoped Access Administrator or Audit Authority grant |

Project-scoped Audit Authority grants never authorize either route. Access
Administrator is already system-only. Both actions are administrative kernel
actions. `actor.profile.read` accepts only a frozen
`ActorProfileAdminReadResourceContext` with
`resource_type: Literal["actor_profile"]`, the requested actor UUID as
`resource_id`, and `read_kind: Literal["profile"]`.
`actor.identity_link.read` accepts only a separate frozen
`ActorIdentityLinkAdminReadResourceContext` with the same resource type and
requested actor UUID but `read_kind: Literal["identity_link"]`. Exact class and
read-kind pairing is enforced in the kernel and covered by negative cross-pair
tests. The server composes these contexts from the path and route; clients never
submit an ActionId, PermissionId, role, scope, or resource fact.

The profile response contains exactly `actor_profile_id`, `actor_kind`,
`status`, `provisioning_method`, `service_identity`, `display_name`,
`created_at`, `updated_at`, `last_seen_at`, `suspended_at`, and
`deactivated_at`. `service_identity` is the closed `ServiceIdentity` enum for a
service actor and is null for a human; it is the stable local lifecycle target
name, not external identity or authority. The identity-link response is one
object, not a collection, and contains exactly `identity_link_id`,
`actor_profile_id`, `subject_kind`, `status`, `linked_at`, `last_verified_at`,
`revoked_at`, and `reactivated_at`. Both schemas forbid extra fields and enforce
the actor-kind/service-identity invariant.

The routes may return active, suspended, or deactivated target profiles and
active or revoked target links because those lifecycle states are the subject
of later administration. They may return human or service targets. They never
return issuer, subject, `contact_email`, raw lifecycle reason, `created_by`,
`linked_by`, lifecycle actor IDs, token or claim data, grant or assignment data,
or any static service-action membership.

## Authorization, lookup, and transaction contract

The caller-owned transaction follows one order:

1. resolve the already-supported human caller and exact verified identity link;
2. lock and revalidate the caller profile first and its exact link second;
3. require and lock the exact effective system-scoped Access Administrator or
   Audit Authority grant for the route's active action and requested UUID;
4. only after the allowed decision, use `ActorService` and the existing
   `ActorRepository.get_actor_profile()` / `get_identity_link_for_actor()` exact
   lookup methods; the router and `AdminAuthorizationRepository` add no duplicate
   actor target SQL;
5. if the target is absent, roll back the staged allowed decision and return the
   same `404 actor_resource_not_found` envelope for a missing actor or link;
6. for a present target, stage only the caller's normal post-authorization
   verification timestamp touch, serialize the strict response, and commit the
   decision evidence and caller touch once in the route.

Unauthorized callers are denied before any target existence query. The public
denial contains no target fields or counts. Missing actor and missing link
responses have identical status, code, and message; no list, alternate field
shape, or pre-authorization lookup provides an existence oracle. The contract
does not claim constant-time database behavior.

The caller profile, exact caller link, and matched grant locks are held through
target lookup, timestamp touch, response composition, and commit. Two-session
barrier tests race both reads against caller suspension, caller deactivation,
caller-link revocation, and matched-grant revocation; disclosure is linearized
before the lifecycle/grant change or denied after it, and no timestamp advances
after the disabling change. These reads do not acquire `AuthorityControl`, do
not lock or mutate a distinct target as a read target, and are not charged to
the administrative mutation limiter. They use the existing shared-session
transaction and do not add a second session, generic teardown commit, read-side
idempotency, or invalidation event.

SQL failure during authorization evidence, target lookup, timestamp touch, or
commit rolls back every staged change and maps to the retryable
`service_unavailable` 503 envelope. A 404, denial, validation failure, or 503
does not advance verification timestamps. On a successful 200, only the
verified caller's `ActorProfile.last_seen_at`, `ActorProfile.updated_at`, and
exact `ActorIdentityLink.last_verified_at` may advance. If the caller requests
their own actor or link, those same rows advance solely in their caller role;
there is no additional target-read touch.

## Evidence and API contract

Each successful read persists one `SensitiveAuthorizationAllowed` decision for
the exact action, permission, actor-profile resource UUID, matched system grant,
request ID, and correlation ID. Denials retain the existing bounded evidence
mapping. The APIs add one generated manifest declaration per route and strict
OpenAPI response models. Path UUID validation may return the standard bounded
422 envelope but must not perform actor lookup or emit private identity data.

Exactly two actions become active: the catalogue remains 65 actions total and
moves from 10 active / 55 planned to 12 active / 53 planned. AUTH-09C activates
no mutation, service, ART, REV, CON, task, project, or grant action.

## Acceptance criteria

- Access Administrator and Audit Authority each succeed only with an effective
  system-scoped grant; project-scoped Audit Authority and every other role fail.
- Suspended/deactivated human and service targets plus revoked target links
  remain visible to an authorized caller, while suspended/deactivated callers,
  revoked caller links, service callers, and unsupported subject kinds fail
  before target lookup.
- Missing actor and missing link have the one stable 404 contract after allowed
  authorization and leave no decision evidence or timestamp change.
- Successful reads advance caller verification timestamps monotonically and do
  not touch a distinct target. Self-target tests prove there is one caller touch,
  not a second target touch.
- Caller lifecycle/link and matched-grant race tests prove the authorization
  locks are held through disclosure and commit without `AuthorityControl` or
  target-row locking.
- Response, OpenAPI, validation, audit, and log tests prove all prohibited
  identity, contact, reason, provenance, grant, assignment, and service-matrix
  fields remain absent. Service-target tests prove the response contains only
  the exact closed `service_identity`, including an unverified service target
  with null `last_seen_at` and null link `last_verified_at`; human responses
  require null `service_identity`.
- SQL/evidence/touch/commit failures return retryable 503 and prove rollback of
  evidence and timestamps with no partial product mutation.
- Route-manifest, action-count, exact resource-context, no-mutation-limiter, and
  dependency-teardown behavior tests pass. The audit parity test uses one closed
  expected set of exactly 12 active ActionIds and is not derived from runtime.
- The complete Agent Gates regression inventory passes unchanged except for the
  exact authored AUTH-09B-merged and AUTH-09C-active lifecycle expectations; no
  gate or unrelated assertion is removed, relaxed, skipped, or reordered.
- Focused actor and authorization subsystem branch coverage is each at least 90
  percent; GitHub Backend preserves the repository-wide 78 percent floor.

## Risk and reviewers

L1 / P1. Required: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts/api_contract_e2e.py)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q \
  tests/test_actors.py tests/test_auth.py tests/test_authorization.py \
  tests/test_audit.py tests/test_api_controls.py tests/test_api_contract_e2e.py)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m coverage erase)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m coverage run \
  --branch --source=app.modules.actors -m pytest -q tests/test_actors.py \
  tests/test_auth.py tests/test_authorization.py tests/test_api_controls.py)
(cd backend && .venv/bin/python -m coverage report --precision=2 --fail-under=90)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m coverage erase)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m coverage run \
  --branch --source=app.modules.authorization -m pytest -q \
  tests/test_authorization.py tests/test_actors.py tests/test_auth.py \
  tests/test_api_controls.py)
(cd backend && .venv/bin/python -m coverage report --precision=2 --fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && \
  cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-db> \
  .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "$metadata_dir/result.json" --timeout-seconds 3600 -- \
  .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
git diff --check
```

## Human review focus

Review system-only role separation, action-specific resource contexts,
caller/grant lock lifetime, authorization-before-lookup ordering, the
single-object link contract, caller-only timestamp semantics including
self-target reads, rollback on missing targets and failures, the bounded closed
service identity, and the absence of external identity, lifecycle provenance,
grant, and service-matrix data.

## Stop condition

Stop after merge and signed memory. Do not start AUTH-09D automatically.
