# Chunk Contract: WS-AUTH-001-10B2 — Privacy-Safe Project Role Grant Reads

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Expose privacy-safe contributor candidates and project-role grant history
through three exact authenticated, rate-controlled read actions.

## Why this chunk exists

After 10A establishes durable truth and 10B1 establishes read abuse control,
disclosure, concealment, minimal schemas, and cursor binding form one reviewable
API boundary independent from mutation locking.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md`
- Decision: D33

## Risk class

L1 authorization, privacy, and API disclosure.

## SLA

P1

## Allowed files

```text
backend/app/modules/actors/repository.py
backend/app/modules/authorization/**
backend/app/modules/projects/repository.py
backend/app/api/deps/authorization.py
backend/app/api/router.py
backend/app/core/api_controls.py
backend/app/core/config.py
backend/app/main.py
backend/tests/test_actors.py
backend/tests/test_authorization.py
backend/tests/test_api_controls.py
backend/tests/test_audit.py
backend/tests/test_projects.py
backend/tests/test_config.py
backend/tests/conftest.py
backend/scripts/api_contract_e2e.py
docs/operations_authorization_service.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-10B2.json
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
migration or durable schema changes
issue/revoke routes or mutation behavior
PREP, idempotency, or invalidation changes
task/review/project product cutover
identity-link, contact, skills, reputation, or cross-project activity disclosure
CI/workflow or coverage-threshold changes
```

## Exact surface inventory

| ActionId | PermissionId | Authority | Canonical target | Surface |
|---|---|---|---|---|
| `project.contributor_candidate.list` | `project.role_grant.manage` | covered Project Manager only | canonical project | `GET /api/v1/projects/{project_id}/contributor-candidates` |
| `project_role_grant.list` | `project.role_grant.read` | covered Project Manager or Audit Authority | canonical project | `GET /api/v1/projects/{project_id}/role-grants` |
| `project_role_grant.read` | `project.role_grant.read` | covered Project Manager or Audit Authority | grant joined to canonical project | `GET /api/v1/projects/{project_id}/role-grants/{grant_id}` |

All are human-only, registered as planned by 10A, and owned by
`ActionOwner.AUTH_10B`. 10B2 activates exactly these three rows with their
routes. System grants cover every canonical project for the exact permission;
project scope must equal the server-loaded project. Services, agents, and Space
principals deny before product-row lookup.

## Acceptance criteria

- Each route consumes the 10B1 `authorization_read` dependency exactly once.
  Missing secret/database failure returns established retryable 503; exhaustion
  returns established 429/Retry-After before product-row lookup. Tests cover
  allowed, denied, and concealed requests, prove no nested-dependency double
  consumption, and prove 429/503 occurs before project/grant/candidate SQL.
- Add strict project collection and grant resource contexts. Collection
  `resource_id` equals `scope_project_id` and carries server-loaded project
  status; detail binds grant ID and canonical project ID. Add only these actions
  to the closed human admin read path, action/context map, scope extraction, and
  guards. Candidate project-state eligibility is evaluated inside the kernel
  before its decision completes, producing bounded denial evidence and the
  centralized 404. Grant list/detail deliberately impose no project-state guard.
- Sequence: verified human resolution, non-locking canonical project load,
  exact authorization, lifecycle guard, cursor validation, then row query.
  Detail queries by both project and grant ID. Nothing serializes before allow.
- Central action-aware HTTP translation maps permission/scope denial,
  nonexistent project, terminal/archived candidate project, missing grant, and
  project/grant mismatch for these actions to one identical structured 404.
  Existing rollback, denial restaging/audit commit, and other mappings remain.
  Permission/scope denials persist the existing bounded authorization-denial
  evidence before public 404 translation. Missing projects/grants, path
  mismatches, and lifecycle concealment do not fabricate authorization-denial
  evidence except candidate terminal/archived status, which is an evidenced
  kernel resource-guard denial after canonical project load. Tests prove each path.
- A composed human-only prelookup dependency rejects every verified nonhuman
  subject kind before `ProjectRepository.get_project`. This includes fixed
  services and the currently unsupported agent and Space kinds, and intentionally
  fails earlier than the general actor-resolution boundary for these three
  privacy-sensitive routes. Because no canonical project exists at
  this point, this prelookup rejection does not fabricate an action decision or
  authority audit event. It returns the same public 404 and tests prove zero
  project/candidate/grant query. It never constructs a canonical context from
  the path parameter and never catches `AuthorizationDenied` in the route.
- Candidate SQL filters active human profile, active identity link, and caller
  exclusion before keyset and `limit + 1`; orders ascending by
  `(created_at, actor_profile_id)`; executes no count; and returns only ID plus
  nullable display name. Active-link eligibility uses `EXISTS`, not a
  multiplicative join, so each profile occurs once even if bad/legacy data
  exposes multiple eligible links. Current PostgreSQL also enforces the existing
  one-link-per-profile unique constraint, so regression proof binds that
  structural constraint plus the defensive `EXISTS` query rather than inserting
  an impossible second link. Only
  draft, active, and paused projects qualify.
- Grant list/detail remain readable in every existing project state. List
  applies optional status/role before keyset and `limit + 1`, orders ascending
  by `(granted_at, grant_id)`, and executes no count.
- Candidate accepts only `limit` (default 50, 1..100) and cursor (maximum 512).
  Grant list accepts only optional `status=active|revoked`, optional
  `role=submitter|reviewer|adjudicator`, limit, and cursor. List envelopes are
  exactly `{items,next_cursor}` with no total.
- Candidate item is exactly `{actor_profile_id,display_name}` with nullable
  display name. Grant list/detail use `extra="forbid"` and contain exactly:
  `id`, `project_id`, `actor_profile_id`, `role`, `status`, `version`,
  `grant_method`, `qualification_snapshot`, `granted_by_actor_profile_id`,
  `granted_by_admin_role_grant_id`, `granted_at`, `grant_reason`,
  `revoked_by_actor_profile_id`, `revoked_at`, and `revoked_reason`. The final
  three revocation fields are present and nullable. The nested snapshot is also
  strict and contains exactly `id`, `requested_role`, `skills_snapshot`,
  `reputation_snapshot`, `prior_project_work_refs`, `external_expertise_refs`,
  `captured_by_actor_profile_id`, `captured_by_admin_role_grant_id`, and
  `captured_at`. Each skills/reputation object contains exactly `availability`,
  `reference_ids`, and nullable `unavailable_reason`. No issuer, subject, link,
  contact, raw claims, secrets, or cross-project activity is exposed.
- Required private `WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET` is canonical
  Base64 decoding to exactly 32 bytes. Missing/malformed/short/long values fail
  settings/startup. It is absent from dumps, repr, errors, and logs and never
  falls back to auth or rate secrets.
- Cursor is canonical Base64url over a strict versioned payload and HMAC-SHA256.
  Canonical digest binds action, project, normalized optional status/role,
  limit, and ordering; boundary binds aware timestamp and canonical UUID.
  Constant-time verification and bounded decoding reject unknown keys/types,
  encoding/timestamp/UUID noncanonicality, tampering, and cross-action/project/
  filter/limit replay before row query.
- The negative cursor matrix explicitly covers malformed encoding, more than
  the bounded decoded bytes, unknown version, unknown/missing/extra key, wrong
  field type, noncanonical Base64url, timestamp, or UUID, bad signature, and
  cross-action/project/status/role/limit/order replay. Every case fails before
  row SQL and returns the same invalid-cursor response.
- Both ascending keysets use boundary tuple `(timestamp, UUID)` and SQL
  `> (timestamp, UUID)` semantics (or the equivalent strict disjunction), fetch
  `limit + 1`, and encode the last visible item only when another row exists.
  Query digest derives from normalized action/project/status/role/limit/order,
  never raw query ordering or the cursor itself.
- Persistence ownership is exact: `ProjectRepository` owns canonical project
  lookup; `ActorRepository` owns candidate eligibility/keyset SQL; the
  authorization repository owns grant/snapshot list/detail SQL; authorization
  service/router own orchestration and schema conversion. Reuse canonical
  hashing, secret sanitation, and Base64 framing patterns, but do not reuse or
  extend the unsigned administrative-grant cursor codec.
- Tests cover page boundaries/equal timestamps/no gaps, all eligibility and
  project states, PM versus Audit Authority, system versus project scope,
  nonhuman denial, identical concealment plus persisted bounded denial evidence,
  strict schemas/no counts, cursor failures, and secret non-serialization.
- Exactly one active OpenAPI declaration exists per surface and manifest delta
  is exactly three. AUTH-10C actions stay planned and authorization-context is absent.
- Operations/spec docs cover cursor-key generation, provisioning, coordinated
  rotation and startup failure; diagnostics never log cursors/secrets or reveal
  concealment distinctions. They enumerate exact routes, actions, authorities,
  project-state behavior, strict fields/no totals, and the unchanged
  no-migration/no-PREP/no-mutation boundary.
- Hosted `api_contract_e2e.py` provisions an isolated cursor secret and exercises
  all three real routes, identical 404 concealment, OpenAPI action IDs, strict
  shapes, and absence of extra surfaces. Deterministic ASGI dependency tests own
  practical 429/`Retry-After` and retryable 503 injection because making the
  isolated hosted database unavailable would also destroy the server and its
  cleanup boundary; they exercise the real nested rate dependency and prove the
  failure precedes project SQL. The merge intent names only 10B2 and its
  successor 10C.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/actors app/modules/authorization app/modules/projects app/api/deps/authorization.py app/core/api_controls.py app/core/config.py app/main.py tests/test_actors.py tests/test_authorization.py tests/test_projects.py tests/test_config.py scripts/api_contract_e2e.py)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python scripts/run_isolated_tests.py --metadata-json <path> --timeout-seconds 300 -- .venv/bin/python -m pytest -q tests/test_actors.py tests/test_authorization.py tests/test_projects.py tests/test_config.py -k 'project_role or contributor_candidate or pagination_cursor or authorization_read')
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

GitHub owns full shards, aggregate 78 percent coverage, authorization subsystem
90 percent coverage, API E2E, and Agent Gates.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Review rate-before-lookup, canonical scope, identical audited concealment,
filter-before-keyset behavior, minimal fields, cursor binding, and exact activation.

## Preimplementation plan-review resolution

- Dependency precedence is exact: verified token, one `authorization_read`
  consumption, actor resolution plus human-only admission, canonical project
  load, kernel authorization, cursor validation, then row query. For every
  verified token, exhausted 429 or private retryable 503 therefore precedes the
  identical nonhuman 404. Tests cover human, service, agent, Space, concealed,
  missing-resource, and invalid-cursor paths at this ordering.
- Candidate project-state eligibility remains a typed resource guard inside the
  single `AuthorizationService.require` decision. Grant list/detail deliberately
  carry no project-state guard.
- Cursor-secret parsing and redaction land before route activation and startup
  validates the required canonical Base64 32-byte value. There is no default,
  test compatibility value, auth/rate-secret fallback, or serialization path.
  Coordinated rotation intentionally invalidates outstanding cursors and requires
  quiescence plus restart across replicas. The shared pytest harness explicitly
  provisions an isolated test-only value because startup validation applies to
  every application fixture; this is environment provisioning, not a Settings
  default or compatibility fallback.
- Permission/scope and candidate lifecycle denials retain dependency-owned
  rollback, bounded denial restaging, commit, and identical 404 translation.
  Evidence persistence failure maps to private retryable 503. Missing project or
  grant, project/grant mismatch, and nonhuman prelookup rejection create no
  fabricated decision or audit row; routes neither catch `AuthorizationDenied`
  nor commit.
- Activation is atomic with the complete route boundary: exactly the three
  existing `ActionOwner.AUTH_10B` rows and three OpenAPI operations become
  active. AUTH-10C remains planned. No CI workflow, threshold, skip, xfail, or
  fixture-scope workaround is permitted; any required file outside the contract
  is a stop for contract amendment.
- Final architecture review confirmed that rejecting every verified nonhuman
  token immediately after the durable rate gate is the smaller route-specific
  boundary: it avoids actor-registry and product SQL and emits no fabricated
  action decision. The earlier fixed-service-only wording is superseded;
  general actor resolution remains unchanged for every other route.
- The existing exact OpenAPI inventory gate must move from 62 to 65 routes and
  record precisely these three actions. `backend/tests/test_api_controls.py` is
  allowed only for that strengthened manifest regression; no inventory
  assertion may be removed or loosened.
- The existing action-aware audit registry test must add the same exact three
  active actions. `backend/tests/test_audit.py` is allowed only for that closed
  active-set parity assertion; no audit validation may be weakened.

## Stop conditions

Stop on client project truth, authorization after row query, count leakage,
unaudited route-local denial interception, persistence, or capability from read.
