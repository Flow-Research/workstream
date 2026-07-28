# WS-AUTH-001-11B PR Trust Bundle

## Chunk

`WS-AUTH-001-11B` - Project Identity And Actor Context Cutover (L1/P1).

## Goal

Make project identity and the caller's project authorization context depend
only on canonical Workstream grants, with no token-role fallback.

## Human-approved intent

The user approved resuming AUTH-11 while ART proceeds independently and required
each critical authorization chunk to be re-reviewed before implementation.

## What changed and why

- Activated only `project.read` and `actor.authorization_context.read`.
- Hard-cut `GET /api/v1/projects/{project_id}` to local admin/project grants.
- Added `GET /api/v1/actors/me/authorization-context?project_id=...`.
- Added distinct full-admin and minimal-contributor project schemas.
- Added typed project/self-project resource contexts, project-role matched
  authority evidence, scope-aware denials, and missing-project evidence.
- Added human read admission, durable rate control, concealment, and current
  actor/link revalidation to both reads.
- Added an AUTH-owned context projection of active, route-backed project actions
  with shared project-lifecycle guards.
- Added an independent hosted `app/modules/projects/*` 90% coverage gate.

These changes remove issuer token roles from project-read authority and prevent
the context route from becoming a project-existence or capability oracle.

## Design chosen

Routers resolve the canonical project, the kernel owns authorization and audit
evidence, project service owns response projection, and AUTH read service owns
the context read model. Missing selectors use a bounded AUTH selector solely for
denial evidence. Matched grants are locked through context projection.

## Alternatives rejected

- Token-role fallback or dual authorization.
- Empty authorization contexts for projects the caller cannot access.
- Repeated per-action `require()` calls that would create synthetic audit events.
- One project schema that could accidentally leak admin-only fields.
- Route-local concealed errors without central denial evidence.

## Scope control

No project mutations, grant mutations, setup/policy/guide read cutovers,
collection endpoint, new migration, or compatibility alias was added. AUTH-11C
actions remain planned.

## Product behavior

Operator, covered Project Manager, Finance Authority, and Audit Authority grants
receive the registered full project identity. Exact-project Submitter, Reviewer,
or Adjudicator grants receive id, name, and status only. Access Administrator
alone and token roles are denied. The context route returns only relevant role
names and active project actions for the exact project.

## Acceptance criteria proof and test delta

Tests cover catalogue activation, admin/project-role evidence, admin precedence,
minimal projection, cross-project and revoked-grant denial, suspended actor,
revoked exact link, missing-project evidence, rate-before-lookup, nonhuman
concealment, planned-action exclusion, archived lifecycle filtering, OpenAPI,
and real API E2E expectations. Existing token-role project-read success was
intentionally changed to concealed denial.

## Tests and checks run

Local focused tests, Ruff, OpenAPI controls, compile/docstring checks, stale
wording and authorization scans, Markdown links, lightweight agent gates, and
`git diff --check` passed. Full database-backed semantic lanes, API E2E, and
coverage run in GitHub Actions because the local machine is intentionally not
used for the multi-hour full suite.

## CI integrity

The existing four semantic lanes, API E2E, repository-wide 78% floor, actor 90%
floor, and authorization 90% floor are unchanged. The project 90% floor is
additive. No skipped failure, threshold reduction, or bypass was introduced.

## Reviewer results

Architecture, security, QA, product/ops, senior engineering, and CI integrity
all passed after their findings were fixed. Detailed evidence is in
`WS-AUTH-001-11B-internal-review-evidence.md`.

## External review

GitHub Actions and CodeRabbit are pending until the PR is opened.

## Remaining risks and follow-up

Hosted Backend must prove the database-backed route test, API E2E, full suite,
and all coverage floors. Future project-action activation must update the
explicit context-action inventory. AUTH-11C1 and 11C2 remain separate chunks.

## Human review focus

Review exact grant precedence, minimal contributor fields, missing/cross-project
concealment with evidence, matched-grant locking, and context action filtering.

## Human merge ownership

Only the user may approve and merge this PR.
