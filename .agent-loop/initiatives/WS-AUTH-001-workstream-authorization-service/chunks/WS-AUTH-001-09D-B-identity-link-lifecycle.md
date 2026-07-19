# Chunk Contract: WS-AUTH-001-09D-B - Identity-Link Lifecycle And Race Closure

Initiative: `WS-AUTH-001` | Risk: L1 / P1 | Status: implemented and internally reviewed

## Goal

Activate exact identity-link revoke/reactivate behavior and close the mixed
profile, link, and grant final-Access-Administrator concurrency matrix on the
single authorization foundation established by 09D-A.

## Why This Chunk Exists

AUTH-09D-A made lifecycle evidence, invalidation direction, transaction order,
and final-administrator locking truthful. Its migration intentionally
pre-registered identity-link lifecycle provenance and denial vocabulary, while
leaving the two link actions inactive. This child supplies only their public
administrative behavior and the remaining cross-operation race proof.

## Start Gate

AUTH-09D-A merged through PR #148 as `99ae4c9`; signed schema-v2 memory
`cf8a3e8` stopped and named this child; the user then explicitly started it.
Implementation begins only after this exact contract passes required L1 review.

## Allowed Files

```text
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/runtime.py
backend/app/modules/authorization/repository.py
backend/app/modules/authorization/service.py
backend/app/modules/authorization/lifecycle_schemas.py
backend/app/modules/authorization/lifecycle_service.py
backend/app/modules/authorization/router.py
backend/tests/test_authorization.py
backend/tests/test_auth.py
backend/tests/test_api_controls.py
backend/tests/test_api_rate_controls.py
backend/tests/test_audit.py
backend/scripts/api_contract_e2e.py
scripts/test_agent_gates.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/architecture_data_model.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-09D-B.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

The lifecycle service owns orchestration only. It reuses the existing
reservation, authority decision, idempotency completion, append-only audit,
invalidation, actor touch, limiter, error, route-owned commit, and
`AdminAuthorizationRepository` primitives. `authorization/service.py` may only
bind the two existing link operation-evidence entries to their exact ActionIds.
Exact implementation discovery may remove an allowed path; adding a path
requires contract repair and renewed preimplementation review before editing it.

## Not Allowed

```text
Alembic migration or historical migration edit
actor-profile schema, model, or lifecycle behavior change
new identity link, actor replacement, link deletion, or issuer/subject rewrite
AdminRoleGrant or ProjectRoleGrant mutation or grant restoration
fixed-service admission or service-action activation
project, contributor, task, submission, check, review, revision, artifact,
payment, contribution-record, or reputation behavior
compatibility route, alias, fallback, dual path, or legacy response
parallel ledger, authorization kernel, unit of work, session, or database engine
AUTH-09E or another initiative's implementation
```

## Exact Surface And Authority

```text
POST /api/v1/actor-identity-links/{identity_link_id}/revoke
POST /api/v1/actor-identity-links/{identity_link_id}/reactivate
```

The routes declare and activate only the identically named ActionIds and
PermissionIds. Each requires an effective system-scoped Access Administrator,
the admin mutation limiter, a UUID `Idempotency-Key`, and exactly
`{ "reason": "..." }`. Audit Authority, project-scoped authority, fixed-service
callers, token roles, and every other candidate deny before target disclosure.

The shared lifecycle body trims both ends, requires 1 to 500 UTF-8 bytes after
trimming, rejects NUL and unknown fields, and freezes the normalized value for
persistence and digest derivation. Validation returns a non-echoing 422.

## Public Response

Success and exact replay return exactly:

```json
{
  "resource_type": "actor_identity_link",
  "resource_id": "uuid",
  "version": null,
  "http_status": 200
}
```

No actor ID, issuer, subject, contact data, raw reason, lifecycle attribution,
event ID, grant data, or digest is returned. The idempotency record stores only
this typed resource reference.

## State And Field Contract

| Operation | Allowed state | Mutation | New-key conflict |
|---|---|---|---|
| revoke | link `active`; owner `active` or `suspended` | set `revoked`; write caller, database time, normalized reason; preserve prior reactivation provenance | `identity_link_already_revoked` or `actor_deactivated_terminal` |
| reactivate | link `revoked`; owner `active` or `suspended` | set `active`; clear revoke fields; write caller, database time, normalized reason; preserve immutable issuer/subject binding | `identity_link_not_revoked` or `actor_deactivated_terminal` |

Human and fixed-service links are valid targets. A suspended profile's link may
be repaired, but the actor remains unable to authenticate. A deactivated
profile is terminal and its link cannot change. Reactivation does not admit a
fixed service, restore any grant, or advance target verification timestamps.

Self-link revoke returns 403 `resource_guard_denied` before target disclosure.
A caller whose own link is revoked fails authentication and cannot reactivate
itself. An authorized missing link returns the existing privacy-safe 404
`resource_not_found` code after exact permission match. It rolls back the
reservation and provisional denial, then restages and commits exactly one
privacy-safe denial in a clean transaction. It leaves no pending claim,
advances no timestamp, and leaves the key reusable. No allow decision exists
for a missing target.

Each domain conflict rolls back the pending reservation and staged allow, then
commits one `SensitiveAuthorizationDenied` row in a clean transaction with the
exact link ActionId/PermissionId, exact link resource, owning ActorProfile
target, categorical `authorization_evaluation` reason, exact denial code, and
no matched-grant or idempotency reference. The losing key remains reusable.

## Evidence And Invalidation

- Success evidence uses the exact link as entity/resource and binds the owning
  target ActorProfile without exposing issuer or subject.
- Its single invalidation obligation targets the owning ActorProfile authority
  projection.
- Revocation records `effective=true -> effective=false`; reactivation records
  `effective=false -> effective=true`. These facts describe the link component,
  not whole-actor authenticatability or current authority.
- State, attribution, caller touch, success evidence, invalidation,
  idempotency completion, and commit are one atomic transaction.

## Reservation, Lock, And Transaction Order

Every new request follows the reviewed 09D-A order:

1. validate and freeze the request;
2. reserve idempotency as the first database write;
3. authorize the exact action;
4. inside authorization, lock `AuthorityControl(id=1)`, caller profile, caller
   link, and the exact matched caller grant;
5. only after permission match, resolve the immutable owner ID from the target
   link, then lock the owning target profile, exact target link, and any active
   system Access Administrator target grant;
6. disclose replay or mismatch only after current authority succeeds;
7. enforce self, owner, link-state, and final-administrator guards;
8. mutate, touch only the verified caller, append one success and one
   invalidation, complete idempotency, and commit once.

The singleton lock serializes profile, link, and grant authority loss. Link
revocation of a currently effective human Access Administrator fails with 409
`last_access_administrator` when the post-transition count would be zero. The
count requires active human profile, active exact link, and active system Access
Administrator grant. Link reactivation is not a final-admin loss.

Target locking must use one canonical repository method. It accepts the link ID,
resolves the immutable owning profile ID after permission match, then takes
database locks in the established profile/link/grant order and validates the
association. Its return tuple may remain link/profile/grant. It does not
introduce another lifecycle lookup or lock path. The same order is required
because actor-self GET/PATCH/timestamp touch locks profile before link and does
not take the authority singleton.

## Replay, Failure, And Timestamp Contract

- Exact replay reauthorizes, returns the stored link reference even if later
  state changed, and advances only the successful human caller's verification
  timestamps.
- Changed reason or target under the same operation returns
  `idempotency_mismatch` only after reauthorization. Operation is part of the
  namespace, so using the same UUID for the other link operation is independent.
- Validation, rate limit, denial, missing target, conflict, mismatch, and every
  SQL/evidence/completion/commit failure advance no timestamp.
- Authorization evidence, target lookup, reservation, state flush, caller
  touch, success evidence, invalidation, completion, and commit failures return
  the stable retryable 503 envelope with no partial state, evidence, timestamp,
  or pending claim.
- Target `ActorProfile.last_seen_at` and `ActorIdentityLink.last_verified_at`
  never advance for administrative link mutation.

## Acceptance Criteria

- Exactly two actions activate. Catalogue totals become 65 actions, 17 active,
  and 48 planned, with one generated manifest declaration per route.
- State, attribution, exact action decision, link success evidence,
  ActorProfile invalidation, and idempotency completion commit atomically.
- Behavior matrices cover human/service targets, active/revoked links,
  active/suspended/deactivated owners, self guard, target concealment,
  replay/mismatch, authority loss, rollback, timestamps, rate limits, OpenAPI,
  manifest parity, exact allow/deny ActionId/PermissionId audit parity, and
  privacy canaries. Link mismatch evidence carries the exact link ActionId.
- Parameterized PostgreSQL failure injection covers reservation, authorization
  evidence, target lookup, state flush, caller touch, success evidence,
  invalidation, idempotency completion, and commit for one valid revoke and one
  valid reactivate. Every case returns the stable retryable 503 and asserts exact
  pre/post equality for profile, link, grant, evidence, and verification
  timestamps, no pending claim, and a reusable key where reservation began.
- Real PostgreSQL tests cover the following normative races without sleeps:

| Initial state and blocker order | Exact committed outcome |
|---|---|
| active link; same key, same revoke | one 200 success and one 200 exact replay; one link success and one invalidation; no denial; key completed; final revoked |
| revoked link; same key, same reactivate | one 200 success and one 200 exact replay; one link success and one invalidation; no denial; key completed; final active |
| active link; different revoke keys | one 200 success and one 409 `identity_link_already_revoked`; one success/invalidation pair and one denial; winner completed, loser reusable; final revoked |
| revoked link; different reactivate keys | one 200 success and one 409 `identity_link_not_revoked`; one success/invalidation pair and one denial; winner completed, loser reusable; final active |
| active link; revoke holds singleton first | revoke 200 then reactivate 200; two success/invalidation pairs, no denial, both keys completed; final active |
| active link; reactivate holds singleton first | reactivate 409 `identity_link_not_revoked`, then revoke 200; one success/invalidation pair and one denial; revoke key completed, reactivate key reusable; final revoked |
| revoked link; reactivate holds singleton first | reactivate 200 then revoke 200; two success/invalidation pairs, no denial, both keys completed; final revoked |
| revoked link; revoke holds singleton first | revoke 409 `identity_link_already_revoked`, then reactivate 200; one success/invalidation pair and one denial; reactivate key completed, revoke key reusable; final active |
| two effective admins A/B; A profile-disables B before B link-revokes A | profile loss 200; B then denies with the exact suspended/deactivated current-authority code; one lifecycle success/invalidation pair and one authorization denial; A remains the sole effective admin; success key completed and denied key reusable |
| two effective admins A/B; B link-revokes A before A profile-disables B | link revoke 200; A then denies `identity_link_revoked`; one link success/invalidation pair and one authorization denial; B remains the sole effective admin; success key completed and denied key reusable |
| two effective admins A/B; A link-revokes B before B grant-revokes A | link revoke 200; B then denies `identity_link_revoked`; one link success/invalidation pair and one authorization denial; A remains sole effective admin; success key completed and denied key reusable |
| two effective admins A/B; B grant-revokes A before A link-revokes B | grant revoke 200; A then denies `permission_not_granted`; one grant success/invalidation pair and one authorization denial; B remains sole effective admin; success key completed and denied key reusable |
| three effective admins A/B/C; A profile-disables B, B link-revokes C, C grant-revokes A, with A then C holding the singleton first | A and C return 200, B denies the exact current-authority code; exactly two success/invalidation pairs and one authorization denial; B profile and A grant carry the two losses, C link remains active, and C is the sole effective admin; success keys completed and denied key reusable |
| active target link; target self GET holds profile lock first | GET returns 200 and advances the target/self profile and link verification timestamps exactly once; revoke waits, then returns 200 and advances only its separate admin caller; final target link revoked; one link success/invalidation pair; lifecycle key completed; no deadlock |
| active target link; target self PATCH holds profile lock first | PATCH returns 200 and advances the target/self profile and link verification timestamps exactly once; revoke waits, then returns 200 and advances only its separate admin caller; final target link revoked; one link success/invalidation pair; lifecycle key completed; no deadlock |
| active target link; revoke holds target profile lock before target self GET | revoke returns 200 and advances only its admin caller; GET waits then denies `identity_link_revoked` and advances neither target timestamp; final target link revoked; one link success/invalidation pair plus one authorization denial; lifecycle key completed; no deadlock |
| active target link; revoke holds target profile lock before target self PATCH | revoke returns 200 and advances only its admin caller; PATCH waits then denies `identity_link_revoked` and advances neither target timestamp; final target link revoked; one link success/invalidation pair plus one authorization denial; lifecycle key completed; no deadlock |

Every race asserts no deadlock, no pending claim, exact success/invalidation/
denial counts, completed or reusable key disposition, and final profile/link/
grant state. Blocker-controlled PostgreSQL sessions establish order, and the
test must observe the waiter in `pg_stat_activity` with
`wait_event_type = 'Lock'`; timing sleeps are not lock evidence.
The actor-self rows are one parameterized matrix over both GET and PATCH and
both blocker orders; proving only one endpoint or one order fails acceptance.

- Responses, errors, logs, OpenAPI, and evidence exclude issuer, subject, email,
  token data, raw reason, attribution IDs, matched-grant internals, and digests.
- Focused authorization branch coverage is at least 90.00 percent. Actor
  runtime is unchanged and its 09D-A coverage proof is not re-run as a false
  delta metric.
  GitHub Backend preserves the repository-wide 78 percent floor.
- Authorization spec, operations runbook, and live data model document link
  lifecycle administration, component-scoped effectiveness, final-admin guard,
  and non-restoration of grants. Archived reference specifications do not
  change.

## Verification Commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts/api_contract_e2e.py)
(metadata_dir="$(mktemp -d)"; trap 'rm -rf "$metadata_dir"' EXIT; \
  cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-db> \
  .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "$metadata_dir/focused.json" --timeout-seconds 3600 -- \
  .venv/bin/python -m pytest -q \
  tests/test_authorization.py tests/test_audit.py tests/test_api_controls.py \
  tests/test_api_rate_controls.py \
  tests/test_auth.py::test_actor_identity_link_lifecycle_real_postgres_matrix \
  tests/test_auth.py::test_actor_identity_link_lifecycle_real_postgres_concurrency)
(metadata_dir="$(mktemp -d)"; trap 'rm -rf "$metadata_dir"' EXIT; \
  cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-db> \
  .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "$metadata_dir/authorization-coverage.json" \
  --timeout-seconds 3600 -- \
  bash -lc '.venv/bin/coverage erase && .venv/bin/coverage run --branch \
  --source=app/modules/authorization -m pytest -q \
  tests/test_authorization.py \
  tests/test_auth.py::test_signed_tokens_bootstrap_and_admin_grant_lifecycle \
  tests/test_auth.py::test_actor_profile_lifecycle_real_postgres_matrix \
  tests/test_auth.py::test_actor_profile_lifecycle_real_postgres_concurrency \
  tests/test_auth.py::test_actor_identity_link_lifecycle_real_postgres_matrix \
  tests/test_auth.py::test_actor_identity_link_lifecycle_real_postgres_concurrency && \
  .venv/bin/coverage report --precision=2 --fail-under=90')
(metadata_dir="$(mktemp -d)"; trap 'rm -rf "$metadata_dir"' EXIT; \
  cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<local-admin-db> \
  .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "$metadata_dir/api-contract.json" --timeout-seconds 3600 -- \
  .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
git diff --check
```

The two named PostgreSQL nodes are created by this chunk and are mandatory
implementation proof. Full Backend CI remains the authoritative repository-wide
78 percent floor and integration regression gate.

## Required Reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human Review Focus

Review permission-before-disclosure, self-link safety, terminal owner behavior,
component-scoped reactivation, link-to-profile evidence binding, truthful
invalidation direction, singleton serialization across profile/link/grant loss,
final-administrator preservation, caller-only timestamps, and rollback
atomicity.

## Stop Condition

Stop after merge and signed memory. Do not start
`WS-AUTH-001-CONTRIBUTOR-FOUNDATION`, `WS-AUTH-001-09E`, or another initiative
automatically.
