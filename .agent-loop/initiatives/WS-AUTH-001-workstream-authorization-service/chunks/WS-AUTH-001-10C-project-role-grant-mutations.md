# Chunk Contract: WS-AUTH-001-10C - Project Role Grant Mutations

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Status and prerequisite

Active for implementation. AUTH-10B2 merged through PR #178 as
`73b457925b02301587b83d01ced0adb66319d134`. Signed automation run
`30014637065` activated this exact child on protected main
`bcf1292e1a591e3e84bf8ee212ee7191d80741fa`. Chat and local branch state are
not authority; the signed automation projection is the canonical start proof.

## Goal

Issue and revoke independent project contributor roles through PREP-bound,
idempotent, auditable, exact-project transactions.

## Why this chunk exists

Multi-principal locking, absence serialization, replay disclosure, audit,
invalidation, and failure atomicity require a mutation-only security review.

## Risk class

L1 authorization mutation and concurrency.

## SLA

P1

## Allowed files

```text
backend/app/modules/actors/repository.py
backend/app/modules/authorization/**
backend/app/modules/audit/schemas.py
backend/alembic/versions/0034_project_role_issue_evidence.py
backend/tests/conftest.py
backend/tests/test_alembic.py
backend/tests/test_audit.py
backend/app/modules/projects/repository.py
backend/app/api/router.py
backend/tests/test_actors.py
backend/tests/test_authorization.py
backend/tests/test_api_controls.py
backend/tests/test_projects.py
backend/scripts/api_contract_e2e.py
docs/operations_authorization_service.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-10C.json
.agent-loop/REVIEW_LOG.md
```

## Not allowed changes

```text
durable schema changes other than the exact 0034 idempotency/evidence/fact-validator repair below
read/candidate surface redesign
task assignment or review reconciliation implementation
admin/service/project-role authority substitution
`both`, replacement, automated grants, or role conversion
commit inside PREP, kernel, service, or repository
```

## Exact surface inventory

| ActionId | PermissionId | Authority | Surface |
|---|---|---|---|
| `project_role_grant.issue` | `project.role_grant.manage` | covered Project Manager only | `POST /api/v1/projects/{project_id}/role-grants` |
| `project_role_grant.revoke` | `project.role_grant.manage` | covered Project Manager only | `POST /api/v1/projects/{project_id}/role-grants/{grant_id}/revoke` |

Both are human-only and registered as planned by 10A with
`ActionOwner.AUTH_10C`. They remain planned and non-callable until this exact
10C child is separately started and implements them; 10C then changes each row
to active atomically with its route. They use existing mutation rate controls.
Audit Authority, Access Administrator, Operator, Finance Authority, contributor
grants, services, agents, and Space do not substitute for Project Manager
authority.

## Exact lock and transaction order

The route consumes the existing admin-mutation rate dependency exactly once,
opens one root transaction, and reserves or locks the idempotency record before
any other mutable row. Reservation outcome is internal only: mismatch and replay
never branch to a response until PREP and current project authority have been
revalidated, so authority and concealment win over key-existence disclosure.
Fresh, replay, and mismatch paths use the same ordering.

PREP then locks `AuthorityControl(id=1)` as the shared authorization-order
barrier used by administrative lifecycle mutations. Issue uses a target-aware
prepared input containing the canonical target ActorProfile ID in addition to
the existing project scope and full request digest. PREP sorts the distinct
caller and target ActorProfile UUID strings lexically, locks each profile and
then its selected exact link immediately after that profile, and finally locks
the caller's one deterministic covered Project Manager AdminRoleGrant. The
caller's link is the authenticated exact link; the target link is the unique
active exact link selected deterministically for issue. Missing, inactive, or
nonhuman target facts are retained as a fail-closed prepared outcome rather
than raised immediately: PREP still locks and revalidates the caller's current
authority and the route still locks/revalidates the project before choosing the
public result. An unauthorized or concealed-project caller therefore observes
the same status, code, body, and mutation-free outcome for valid, missing,
inactive, agent, Space, or service targets, without a target-specific early
timing or response branch. All competing profile, link, and
administrative-grant mutations retain `AuthorityControl` for the transaction
lifetime. The barrier is ordering coordination, not final-admin permission or
safety. Revoke has no client-trusted target: PREP binds caller, project, grant
ID, idempotency key, and request digest; the locked grant supplies target facts
only during final resource recomposition. Revoke does not require the stored
target profile or identity link to remain active; a target profile row may be
locked only for deterministic concurrency or audit integrity, never as a
revocation admission gate.

The opaque handle binds action, caller/link, target when issue, project, role
when issue, grant ID when revoke, idempotency key, and full canonical request
digest. Consume rejects target, scope, role, grant, digest, session,
transaction, action, handle-owner, reuse, or lifecycle substitution. Forged,
copied, serialized, cross-service, cross-session, and already-consumed handles
fail closed.

After PREP returns, issue locks canonical project, then takes one transaction
advisory key for `(actor_profile_id, project_id, requested_role)` to serialize
absence, then reloads the target/scope facts and active exact-role selector.
Revoke locks canonical project then the exact path-project grant. Consume
recomposes every fact and evaluates once; repositories flush only. The route
commits once.

The issue advisory key is a domain-separated deterministic PostgreSQL signed
`int8`. Its frozen input encoding is the compact UTF-8 JSON array
`["workstream.project_role_grant.issue.v1","<canonical-lowercase-actor-uuid>","<canonical-lowercase-project-uuid>","<role-value>"]`
with no insignificant whitespace and JSON escaping defined by the repository's
canonical serializer. SHA-256 hashes those exact bytes; the first eight digest
bytes are decoded big-endian as a two's-complement signed `int64`. Tests freeze
a known vector, exact encoding, UUID and role separation, stability, and signed
range.
The partial unique active-exact-role index remains the final backstop; a
uniqueness race becomes `project_role_grant_exists` without a second snapshot,
success event, or grant.

The complete order is: rate consumption -> root transaction -> idempotency
reserve/record lock -> AuthorityControl -> lexical caller/target profile and
exact-link locks -> deterministic covered Project Manager grant -> project ->
issue advisory key or exact revoke grant -> canonical fact reload -> consume
exactly once -> snapshot/grant/idempotency/audit/invalidation flush -> one
route-owned commit. Rollback and denial-evidence restaging never invert this
order or disclose reservation outcome before authorization.

Crossed tests prove two managers targeting one another, issue versus target
profile/link lifecycle, and issue versus caller-grant revocation cannot deadlock
because all paths share the barrier and compatible principal order.

## Exact request and response contract

Issue requires `Idempotency-Key: <uuid>` and a strict body containing exactly
`target_actor_profile_id`, `role`, `qualification`, and `reason`.
`qualification` is identifier-free and contains only the two exact availability
objects and reference lists defined by 10A; the server composes path project,
body target, and body role into `ProjectRoleQualificationSnapshotInput`. The
full canonical bounded qualification value participates in the issue request
digest, idempotency equality, PREP binding, and snapshot validation. Changing
any qualification field with the same key is `idempotency_mismatch`. Revoke
requires the same header and exactly `reason`. Reasons
are 1..500 UTF-8 bytes, equal their Python `str.strip()` result, and contain no
Unicode control character. Issue returns HTTP 201 with exactly `{id,
qualification_snapshot_id, project_id, actor_profile_id, role, status:
"active", version: 1}`. Revoke returns HTTP 200 with the same fields, the
original snapshot ID, `status: "revoked"`, and `version: 2`. Strict response
schemas reject undeclared fields, including identity-link and contact data.
Stable errors are HTTP 400 `invalid_request`, HTTP 403
`self_grant_forbidden` or `self_role_revoke_forbidden`, concealed HTTP 404
`resource_not_found`, HTTP 409 `idempotency_mismatch` or
`project_role_grant_exists`, `project_role_grant_already_revoked`, or
`project_role_grant_replay_state_changed`, HTTP 422
`qualification_snapshot_invalid`, and fail-closed HTTP 503
`service_unavailable`. A same-key/same-body issue replay reauthorizes and
returns the prior canonical HTTP 201 response while the grant remains active;
after that grant is revoked it returns HTTP 409
`project_role_grant_replay_state_changed` without the stale response. A
same-key/same-body revoke replay reauthorizes and returns the prior canonical
HTTP 200 revoked response; a new-key revoke of an already-revoked grant returns
HTTP 409 `project_role_grant_already_revoked`.

Replay never trusts stored response metadata alone. Active issue replay locks
and reloads the canonical path project, grant, and snapshot and requires the
exact project/target/role tuple, snapshot ownership, `status=active`, and
`version=1`. Revoked, missing, or mismatched state becomes
`project_role_grant_replay_state_changed` only after current authority and
project concealment pass. Revoke replay locks and reloads the exact
path-project grant and original snapshot and requires `status=revoked`,
`version=2`, and unchanged ownership before returning the prior HTTP 200 shape.

The shared `AuthorityMutationService` remains the sole completion path. It is
extended to validate and atomically append an ordered tuple of success events
and an optional typed invalidation projection before completing idempotency.
Issue writes exactly `ProjectRoleQualificationSnapshotCaptured` followed by
`ProjectRoleGrantIssued` and creates no invalidation. Revoke writes exactly
`ProjectRoleGrantRevoked` followed by one linked
`AuthorityInvalidationRequested` containing grant, actor, project, role,
cause-event, and the role-specific future-obligation projection. No parallel
completion writer is permitted.

The existing database idempotency completion guard predates the 10A evidence
shape and requires one success plus one invalidation for every operation. That
would either reject 10C issue or force a false invalidation. Migration 0034 is
therefore the sole permitted durable change in this chunk. It replaces only the
exact bodies of `guard_authority_idempotency_record()`,
`validate_linked_authority_event()`, and `authority_event_facts_are_safe()`, and
extends only the existing audit privacy check constraint's resource registry
with `qualification_snapshot`, so
`project_role_grant.issue` requires exactly two non-invalidation events —
`ProjectRoleQualificationSnapshotCaptured` followed by
`ProjectRoleGrantIssued` — with the qualification event bound to the same
idempotency record, request/correlation pair, actor, permission, project, target
actor, and matched Project Manager grant. The qualification event's
entity/resource/target kind and ID are exactly its snapshot ID. The issued event's
entity/resource/target are exactly the response grant ID. The linked-event guard
admits qualification capture only for a pending issue record with no prior linked
event, and admits grant-issued only after exactly one matching qualification
event exists; it rejects reversed, duplicate, extra, cross-record, cross-request,
cross-correlation, cross-actor, cross-permission, cross-project, cross-target,
cross-manager, or false-invalidation shapes. Application tests prove writer call
order; the durable schema claims exact cardinality and predecessor presence, not
a total order derived from timestamp or UUID. Completion additionally requires
the persisted grant's qualification snapshot, project, actor, and role tuple to
match the persisted snapshot and the two audit envelopes. The database proves
their project, target actor, role facts, matched manager, claim, request ID, and
correlation ID linkage. The application `AuthorityMutationService` remains
solely responsible for proving those envelopes against the canonical request
digest stored by idempotency. Issue requires zero invalidations.

The predecessor `authority_event_facts_are_safe()` admits only the two-key
`{"effective": true}` to `{"effective": false}` invalidation shape. That shape
cannot carry AUTH-10C's required role-specific future-obligation projection.
Migration 0034 therefore changes only its
`AuthorityInvalidationRequested` branch: non-project-role-revoke operations
retain the exact predecessor two-key shape, while a linked
`project_role_grant.revoke` event admits exactly five keys — `effective`,
`role`, `scope_type`, `scope_id`, and `future_obligation`. Before and after must
match on every value except `effective`; `scope_type` is exactly `project`,
`scope_id` equals the envelope project ID, and the closed mapping is submitter
to `auth13_assignment`, reviewer to `rev_reviewer_obligation`, and adjudicator
to `none`. `effective` values are JSON booleans and every other value is a JSON
string; nulls, coercion, arrays, objects, missing keys, and extra keys reject.
Because this fact validator receives no operation or idempotency context, it
only admits the exact richer JSON shape. The linked-event validator exclusively
restricts that shape to a linked `project_role_grant.revoke` and preserves all
existing cause, request/correlation, actor, permission, project, target,
matched-grant, idempotency, and resource linkage. No generic additional fact
key or obligation value is admitted. The existing
`ck_audit_events_fact_bounds` constraint remains in place and continues to call
this validator; it is not dropped or recreated. Migration custody does not
extend to `authority_facts_are_safe()`.

Every other operation retains the exact existing success-event allowlist,
response resource/type/status/version binding, one success plus one invalidation,
invalidation cause pointing to that success, actor/project/permission/request/
correlation/idempotency linkage, target projection, and before/after predicates.

Migration 0034 has `down_revision = "0033_authorization_read_rate"`. Upgrade and
downgrade lock `authority_idempotency_records` then `audit_events`, both in
`ACCESS EXCLUSIVE` mode, before definition or row inspection and retain those
locks through replacement. They require frozen predecessor/forward hashes for
all three functions, the `authority_idempotency_guard` and
`audit_events_validate_idempotency` trigger names, enabled state, timing, event,
table, function attachment, non-deferrability, the exact privacy constraint
definition, and the exact definition, table attachment, validated state, and
`authority_event_facts_are_safe()` call of `ck_audit_events_fact_bounds`.
Upgrade permits a pending project-role issue only when it has zero
linked evidence and all response fields are null. It refuses every committed
issue record, every other pending issue shape, linked orphan/mixed/cross-record
issue evidence, and any definition/binding drift. Downgrade refuses every
committed issue record, any linked qualification event, any zero-invalidation
issue shape, every five-key project-role revoke invalidation including orphan,
mixed, or cross-record shapes, and any pending or committed evidence/response
shape the predecessor cannot represent. Predecessor-compatible two-key revoke
invalidation evidence may remain when otherwise valid. Each refusal is
transactional and leaves Alembic head, all three function and trigger
hashes/bindings, both frozen constraint definitions/states, and all rows
unchanged.
Empty safe downgrade restores the exact predecessor definitions; re-upgrade is
deterministic. No table, column, index, enum, trigger identity, or product row
change is permitted beyond those three function bodies and one registry member.

## Acceptance criteria

- Issue permits draft, active, and paused projects; terminal/archived,
  nonexistent, and unauthorized projects deny without target disclosure.
- Revoke remains available for every existing project state so authority can
  always be removed.
- Issue requires a different active canonical human target with its unique
  active link. Agent, Space, service, and self-grant deny stably after current
  caller/project authorization and concealment have been resolved.
- Revoke derives target identity and role only from the locked exact
  path-project grant. After current covered-manager authorization, self-role
  revoke returns HTTP 403 `self_role_revoke_forbidden`; an unauthorized caller
  cannot learn self-ownership and receives the same concealed HTTP 404 as other
  hidden grants. Target suspension or a revoked/missing target identity link
  never blocks revocation, so granted authority cannot become irremovable.
- Issue creates one exact-role snapshot, one manual grant,
  `ProjectRoleQualificationSnapshotCaptured`, and `ProjectRoleGrantIssued` in
  one transaction. It never changes another role.
- Revoke changes only the locked exact role and creates
  `ProjectRoleGrantRevoked` plus one linked `AuthorityInvalidationRequested`
  carrying grant, actor, project, role, and cause-event references.
- Submitter invalidation names only the future AUTH-13 assignment obligation;
  reviewer names only its REV-owned obligation; adjudicator creates no product
  obligation until separately activated.
- Same key/same request replay reloads canonical project, grant, and snapshot
  and reauthorizes the current caller before response disclosure. Suspended,
  revoked-link, removed/out-of-scope manager, or now-concealed project replay
  denies without returning stale response data.
- Same key/different request or role is `idempotency_mismatch`; new-key active
  same-role issue is one audited stable conflict; distinct roles may issue
  concurrently.
- Cancellation and injected failure at snapshot, grant, idempotency, audit,
  invalidation, flush, and commit leave no orphan row or partial evidence.
- Migration 0034 proves exact upgrade/downgrade function/constraint replacement, strict
  refusal/no-mutation on unexpected definitions and incompatible evidence,
  two linked issue events with zero invalidation, and unchanged per-operation
  success/invalidation enforcement for every other authority operation. It also
  proves the exact five-key project-role revoke invalidation fact shape, all
  three closed role-to-obligation mappings, rejection of missing/extra/wrong
  fact keys and values, and unchanged two-key invalidation facts for every
  non-project-role-revoke operation. It independently tests missing, changed,
  detached, unvalidated, or differently bound `ck_audit_events_fact_bounds`
  and proves every refusal leaves the revision, three functions, constraints,
  triggers, and product/evidence rows unchanged. Focused
  Alembic tests cover prior-head upgrade, fresh head, safe downgrade/re-upgrade,
  each definition/trigger/constraint drift, each incompatible evidence predicate
  alone and combined, transactional no-mutation snapshots, concurrent writer
  races, wrong/reversed/extra/cross-linked issue events, false invalidation, and
  a parameterized regression over every non-issue authority operation.
- PostgreSQL tests cover identical-role issue, different-role issue, crossed
  managers, revoke versus regrant, revoke versus authorization, replay after
  authority loss, timeout, and cancellation. PostgreSQL and API tests also
  prove a covered manager can revoke an active grant after the target profile
  is suspended and after its identity link is revoked.
- Live API proof uses the same unexpired manager token to issue, read the active
  grant through 10B, revoke, read the historical revoked grant, and prove a
  same-key/same-body revoke replay returns the prior HTTP 200 response after
  reauthorization while a new-key second revoke returns HTTP 409
  `project_role_grant_already_revoked`; an old issue replay after revocation is
  reauthorized and returns HTTP 409 `project_role_grant_replay_state_changed`
  without stale disclosure or direct database edits. Unit and PostgreSQL tests
  assert the same-key active issue replay remains HTTP 201 and the post-revoke
  issue replay changes to that exact closed conflict.
  Contributor-capability denial remains explicitly deferred to AUTH-11/13 where
  a real consumer action exists.
- Cross-project revoke (`project_id=A`, grant from B), nonexistent grant, and
  unauthorized revoke share concealed 404 and create no mutation, success
  audit, invalidation, or disclosure. Unauthorized issue with and without any
  manager grant cannot distinguish valid, nonexistent, inactive, agent, Space,
  service, or otherwise unauthorized targets: exact public status, code, and
  body match and no mutation/evidence is written. Unauthorized revoke cannot
  distinguish self-owned, cross-project, or nonexistent grants; only an
  authorized covered manager receives the declared self-role 403.
- PostgreSQL concurrency tests use independent sessions, deterministic
  synchronization that observes held and waiting locks, bounded
  `asyncio.wait_for` plus statement/lock timeouts, and clean-retry proof.
  Cancellation while waiting and after each staged flush, plus injected
  route-commit failure, leaves no pending idempotency record, snapshot, grant,
  audit, or invalidation; the route explicitly rolls back/closes and a clean
  retry succeeds.
- Existing 10B read, cursor, concealment, rate-order, exact OpenAPI inventory,
  and protected-action assertions remain intact. Only the two AUTH-10C rows
  move from planned to active; owner and permission remain unchanged. The two
  operations carry exact action IDs, consume the admin-mutation rate dependency
  exactly once, and never attach authorization-read rate consumption.
- Hosted `backend/scripts/api_contract_e2e.py` provisions a distinct canonical
  human target and covered project-scoped Project Manager through existing
  public APIs with unexpired tokens and no direct database edits. The same
  manager token proves issue -> 10B active read -> revoke -> 10B historical
  read -> same-key revoke replay 200 -> new-key revoke 409 -> old issue replay
  409, plus concealed denial after manager authority loss.
- Regenerate exact combined route/protected-operation counts and SHA-256
  inventories from current main after adding the two routes; never guess or
  replace exact hashes with count-only assertions. No migration other than exact
  0034, configuration,
  workflow, pytest marker, skip/xfail, command, or coverage-threshold change is
  allowed. GitHub must pass all shards, hosted E2E, Agent Gates, the 78 percent
  repository floor, and the 90 percent authorization-subsystem floor.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check alembic/versions/0034_project_role_issue_evidence.py app/modules/actors app/modules/authorization app/modules/projects tests/conftest.py tests/test_actors.py tests/test_alembic.py tests/test_audit.py tests/test_authorization.py tests/test_api_controls.py tests/test_projects.py scripts/api_contract_e2e.py)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python scripts/run_isolated_tests.py --metadata-json <path> --timeout-seconds 600 -- .venv/bin/python -m pytest -q tests/test_alembic.py tests/test_audit.py -k '0034 or project_role_issue_evidence or action_aware_audit')
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python scripts/run_isolated_tests.py --metadata-json <path> --timeout-seconds 300 -- .venv/bin/python -m pytest -q tests/test_actors.py tests/test_authorization.py tests/test_api_controls.py tests/test_projects.py -k 'project_role or auth10c')
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

GitHub owns the full sharded suite, aggregate and authorization coverage, API
E2E, and Agent Gates before PR readiness.

Every new migration, fact-validator, constraint-drift, and refusal test in this
chunk must include `0034` or `project_role_issue_evidence` in its test name so
the focused selector above cannot omit required proof.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Review multi-principal lock order, no-self controls, exact-project scope,
replay reauthorization, role-specific invalidation, and single commit ownership.

## Stop conditions

Stop on target-after-caller deadlock ordering, unlocked absence checks, stale
replay disclosure, cross-role mutation, lifecycle implementation, or PREP bypass.
