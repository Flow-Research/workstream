# Chunk Contract: WS-AUTH-001-10C - Project Role Grant Mutations

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Status and prerequisite

Proposed and inactive. Start only after 10B merges, signed memory names 10C,
and a fresh explicit start event activates this exact child.

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
backend/app/modules/projects/repository.py
backend/app/api/router.py
backend/tests/test_actors.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/scripts/api_contract_e2e.py
backend/scripts/auth_api_e2e.py
docs/operations_authorization_service.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-10C.json
.agent-loop/REVIEW_LOG.md
```

## Not allowed changes

```text
migration or durable schema changes
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

Both are human-only, owned by `WS-AUTH-001-10C`, active with their route, and
use existing mutation rate controls. Audit Authority, Access Administrator,
Operator, Finance Authority, contributor grants, services, agents, and Space do
not substitute for Project Manager authority.

## Exact lock and transaction order

PREP first locks `AuthorityControl(id=1)` as the shared authorization-order
barrier used by administrative lifecycle mutations. It then accepts the caller
plus the known target human principal for issuance, sorts distinct ActorProfile
IDs lexically, and locks each profile then its exact active link. It finally
locks the caller's one deterministic covered Project Manager AdminRoleGrant.
The barrier is ordering coordination, not final-admin permission or safety.

After PREP returns, issue locks canonical project, then takes one transaction
advisory key for `(actor_profile_id, project_id, requested_role)` to serialize
absence, then reloads the target/scope facts and active exact-role selector.
Revoke locks canonical project then the exact grant. Consume recomposes every
fact and evaluates once; repositories flush only. The route commits once.

Crossed tests prove two managers targeting one another, issue versus target
profile/link lifecycle, and issue versus caller-grant revocation cannot deadlock
because all paths share the barrier and compatible principal order.

## Exact request and response contract

Issue requires `Idempotency-Key: <uuid>` and a strict body containing exactly
`target_actor_profile_id`, `role`, `qualification`, and `reason`.
`qualification` contains the two exact availability objects and reference lists
defined by 10A. Revoke requires the same header and exactly `reason`. Reasons
are 1..500 UTF-8 bytes, equal their Python `str.strip()` result, and contain no
Unicode control character. Issue returns HTTP 201 with exactly `{id,
qualification_snapshot_id, project_id, actor_profile_id, role, status:
"active", version: 1}`. Revoke returns HTTP 200 with the same fields, the
original snapshot ID, `status: "revoked"`, and `version: 2`. Strict response
schemas reject undeclared fields, including identity-link and contact data.
Stable errors are HTTP 400 `invalid_request`, HTTP 403
`self_grant_forbidden` or `self_role_revoke_forbidden`, concealed HTTP 404
`resource_not_found`, HTTP 409 `idempotency_mismatch` or
`project_role_grant_exists` or `project_role_grant_already_revoked`, HTTP 422
`qualification_snapshot_invalid`, and fail-closed HTTP 503
`service_unavailable`. A same-key/same-body revoke replay reauthorizes and
returns the prior canonical HTTP 200 revoked response; a new-key revoke of an
already-revoked grant returns HTTP 409 `project_role_grant_already_revoked`.

## Acceptance criteria

- Issue permits draft, active, and paused projects; terminal/archived,
  nonexistent, and unauthorized projects deny without target disclosure.
- Revoke remains available for every existing project state so authority can
  always be removed.
- Target is a different active human with active link. Agent, Space, service,
  self-grant, and self-revoke deny stably before disclosure.
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
- PostgreSQL tests cover identical-role issue, different-role issue, crossed
  managers, revoke versus regrant, revoke versus authorization, replay after
  authority loss, timeout, and cancellation.
- Live API proof uses the same unexpired manager token to issue, read the active
  grant through 10B, revoke, read the historical revoked grant, and prove a
  same-key/same-body revoke replay returns the prior HTTP 200 response after
  reauthorization while a new-key second revoke returns HTTP 409
  `project_role_grant_already_revoked`; an old issue replay after revocation is
  reauthorized and denied without stale disclosure or direct database edits.
  Contributor-capability denial remains explicitly deferred to AUTH-11/13 where
  a real consumer action exists.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/actors app/modules/authorization app/modules/projects tests/test_actors.py tests/test_authorization.py tests/test_projects.py scripts/auth_api_e2e.py)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python scripts/run_isolated_tests.py --metadata-json <path> --timeout-seconds 300 -- .venv/bin/python -m pytest -q tests/test_actors.py tests/test_authorization.py tests/test_projects.py -k 'project_role_grant')
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/auth_api_e2e.py)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

GitHub owns the full sharded suite, aggregate and authorization coverage, API
E2E, and Agent Gates before PR readiness.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Review multi-principal lock order, no-self controls, exact-project scope,
replay reauthorization, role-specific invalidation, and single commit ownership.

## Stop conditions

Stop on target-after-caller deadlock ordering, unlocked absence checks, stale
replay disclosure, cross-role mutation, lifecycle implementation, or PREP bypass.
