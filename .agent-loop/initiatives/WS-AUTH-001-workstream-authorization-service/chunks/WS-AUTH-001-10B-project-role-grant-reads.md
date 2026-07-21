# Chunk Contract: WS-AUTH-001-10B - Project Role Grant Read And Candidate Surfaces

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Status and prerequisite

Proposed and inactive. Start only after 10A merges, signed memory names 10B,
and a fresh explicit start event activates this exact child.

## Goal

Expose privacy-safe contributor candidates and project-role grant history
through three exact read actions after 10A establishes durable truth.

## Why this chunk exists

Read disclosure, candidate eligibility, filtering-before-count, and cursor
binding can be reviewed independently from mutation locking.

## Risk class

L1 authorization, privacy, and API disclosure.

## SLA

P1

## Allowed files

```text
backend/app/modules/actors/repository.py
backend/app/modules/authorization/**
backend/app/modules/projects/repository.py
backend/app/api/router.py
backend/app/core/config.py
backend/tests/test_actors.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/tests/test_config.py
backend/scripts/api_contract_e2e.py
docs/operations_authorization_service.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-10B.json
.agent-loop/REVIEW_LOG.md
```

## Not allowed changes

```text
migration or durable schema changes
issue/revoke routes or mutation behavior
PREP extension
task/review/project product cutover
identity-link, contact, skills, reputation, or cross-project activity disclosure
```

## Exact surface inventory

| ActionId | PermissionId | Authority | Canonical target | Surface |
|---|---|---|---|---|
| `project.contributor_candidate.list` | `project.role_grant.manage` | covered Project Manager only | canonical project | `GET /api/v1/projects/{project_id}/contributor-candidates` |
| `project_role_grant.list` | `project.role_grant.read` | covered Project Manager or Audit Authority | canonical project | `GET /api/v1/projects/{project_id}/role-grants` |
| `project_role_grant.read` | `project.role_grant.read` | covered Project Manager or Audit Authority | grant joined to canonical project | `GET /api/v1/projects/{project_id}/role-grants/{grant_id}` |

All are human-only and registered as planned by 10A with
`ActionOwner.AUTH_10B`. They remain planned and non-callable until this exact
10B child is separately started and implements them; 10B then changes each row
to active atomically with its route. They use non-locking canonical project
reads. System-scoped candidates cover every project only for the retained
permission; project scope must equal the loaded project. Services, agents, and
Space principals deny before lookup.

## Acceptance criteria

- Candidate SQL filters active human profile, active link, and caller exclusion
  before total/cursor calculation and returns only ID plus nullable display name.
- Candidate discovery allows draft, active, and paused projects and conceals
  terminal/archived, nonexistent, and unauthorized projects equivalently.
- Grant list/detail remain readable for every existing project state so
  immutable history is inspectable; unauthorized/nonexistent/path-mismatch
  cases are indistinguishable before disclosure.
- Candidate accepts only `limit` (default 50, range 1..100) and `cursor` (at
  most 512 characters). Its item is exactly `{actor_profile_id, display_name}`
  with nullable display name. Grant list accepts only `status` (optional exact
  `active|revoked`), `role` (optional exact
  `submitter|reviewer|adjudicator`), `limit` (default 50, range 1..100), and
  `cursor` (at most 512 characters). Both list envelopes are exactly
  `{items, next_cursor}` and intentionally expose no total count.
- Grant list items and detail responses share one strict schema containing
  exactly `id`, `project_id`, `actor_profile_id`, `role`, `status`, `version`,
  `grant_method`, `qualification_snapshot`,
  `granted_by_actor_profile_id`, `granted_by_admin_role_grant_id`, `granted_at`,
  `grant_reason`, `revoked_by_actor_profile_id`, `revoked_at`, and
  `revoked_reason`. The nested snapshot contains exactly `id`, `requested_role`,
  the two 10A availability objects, `prior_project_work_refs`,
  `external_expertise_refs`, `captured_by_actor_profile_id`,
  `captured_by_admin_role_grant_id`, and `captured_at`. Nullable revocation
  fields remain present. Strict schemas reject all other fields, especially
  identity issuer/subject/link status, contact data, raw claims, and secrets.
- 10B introduces one shared authorization pagination codec using HMAC-SHA256 and
  a required base64-decoded 32-byte
  `WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET`. The versioned cursor payload binds
  action, project, status, exact optional role, limit, boundary timestamp/UUID,
  and canonical query digest. Signature comparison is constant-time;
  malformed/tampered/cross-project/cross-filter cursors reveal neither count
  nor rows. The secret is configuration-only, never logged, serialized, stored,
  or reused from auth/rate-limit secrets.
- Existing read rate control is reused. Every surface has exactly one active
  OpenAPI declaration and manifest-delta proof.
- `/actors/me/authorization-context` remains absent and planned for AUTH-11.
- No write, PREP, idempotency, invalidation, or migration behavior changes.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/actors app/modules/authorization app/modules/projects app/core/config.py tests/test_actors.py tests/test_authorization.py tests/test_projects.py tests/test_config.py)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python scripts/run_isolated_tests.py --metadata-json <path> --timeout-seconds 300 -- .venv/bin/python -m pytest -q tests/test_actors.py tests/test_authorization.py tests/test_projects.py tests/test_config.py -k 'project_role or contributor_candidate or pagination_cursor')
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

GitHub owns the full sharded suite, aggregate and subsystem coverage, API E2E,
and Agent Gates before PR readiness.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Review scope coverage, filter-before-count, lifecycle concealment, minimal
candidate fields, cursor binding, and absence of mutation behavior.

## Stop conditions

Stop on client-supplied project truth, post-query authorization, count leakage,
new persistence, or any contributor capability implied by a read.
