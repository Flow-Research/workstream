# Chunk Contract: WS-AUTH-001-11B - Project Identity And Actor Context Cutover

## Status

Authorized for implementation after AUTH-11A merged in PR #208. Work follows
the repository's simple engineering loop; planning artifacts do not activate or
lock execution.

## Goal

Hard-cut project identity reads to local grants and add a self authorization-
context query that reports only the caller's effective authority for one
canonical project.

## Risk and SLA

L1 / P1

## Allowed files

```text
backend/app/modules/projects/router.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/app/modules/projects/repository.py
backend/app/api/deps/authorization.py
backend/app/api/routes/auth.py
backend/app/modules/actors/schemas.py
backend/app/modules/actors/service.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/read_service.py
backend/app/modules/authorization/repository.py
backend/app/modules/authorization/runtime.py
backend/tests/test_projects.py
backend/tests/test_auth.py
backend/tests/test_actors.py
backend/tests/test_authorization.py
backend/tests/test_api_controls.py
backend/scripts/api_contract_e2e.py
.github/workflows/backend.yml
docs/operations_authorization_service.md
docs/operations_roles_permissions.md
docs/operations_project_operating_manual.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/STATUS.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-11B-project-identity-actor-context.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/reviews/WS-AUTH-001-11B-internal-review-evidence.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/reviews/WS-AUTH-001-11B-pr-trust-bundle.md
```

## Not allowed

```text
project mutation or setup/policy/guide routes
token-role fallback or dual authorization
grant mutation
project collection/list API
```

## Acceptance criteria

- Activate only `project.read` and `actor.authorization_context.read`.
- Resolve the canonical project before authorization; unknown, cross-project,
  unauthorized, inactive-grant, and out-of-scope requests are concealed by the
  action-aware public denial contract. Both 11B actions use the shared denial
  translator and preserve their authorization evidence before returning the
  identical public not-found envelope.
- Eligible scoped admin grants receive the registered project identity view.
  This means Operator system scope and effective system/project-scoped Project
  Manager, Finance Authority, and Audit Authority grants. Access Administrator
  alone is denied because its registered permission set excludes
  `project.read`. All four eligible admin roles share the existing registered
  `ProjectResponse` fields: id, name, slug, description, lifecycle status,
  created_at, and updated_at; 11B does not expose setup, guide, policy, task,
  submission, compensation, or reputation data through this route.
  Active exact-project submitter, reviewer, and adjudicator grants independently
  receive only the minimal project identity projection: project id, name, and
  lifecycle status. Contributor responses omit slug, description, and
  timestamps. A caller with both kinds of authority receives the registered
  admin projection; response selection is server-owned.
- Admin and contributor projections use distinct strict response schemas; the
  minimal contributor projection cannot validate or serialize the omitted
  admin-only fields.
- The context response is self-only, exact-project, derived from current local
  grants and action availability, and cannot advertise planned/inactive actions.
  A caller with no effective local authority for that project receives the same
  concealed not-found response rather than an empty context that confirms the
  project exists.
  It returns the caller actor-profile id and status, the exact project id,
  effective active admin-role names and independent project-role names for that
  project, and the sorted active action ids those grants currently permit. It
  exposes neither grant ids nor identity-link data. Action ids are evaluated
  for the exact canonical project target and limited to active, route-backed
  project actions currently executable there; system, actor-administration,
  and unrelated project actions are excluded.
- Contributor project visibility and context derivation revalidate the current
  human ActorProfile and exact ActorIdentityLink in the request transaction;
  suspension, deactivation, or link revocation denies a stale bearer token even
  while a project-role grant remains active.
- Routers declare one primary ActionId and target; policy stays in the kernel or
  feature policy layer. Both routes use local grants as their sole product-
  authority source after cutover.
- `project.read` uses one typed exact-project resource context and the central
  authorization decision/evidence path. Allowed decisions distinguish a
  matched admin-role grant from a matched project-role grant and persist the
  matched grant plus project scope; no service-layer boolean role check may
  bypass or duplicate the kernel.
- `actor.authorization_context.read` uses a distinct typed self-plus-project
  resource context. An AUTH-owned read projection service derives its strict
  response from canonical grant and catalogue state; actor service remains
  limited to actor-profile behavior and the kernel is not used as a read model.
  Capability derivation does not call `require` once per candidate action or
  stage synthetic per-action decision events.
- Exact-project allow, cross-project deny, role revocation independence,
  minimal-field, concealed-not-found, audit, invalidation, and live API tests
  pass.
- Authorization spec, role matrix, project operating manual, and authorization
  operations docs describe the new context route/schema, project projections,
  concealed denial, and hard removal of token-role authority.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_auth.py tests/test_actors.py tests/test_projects.py tests/test_api_controls.py --cov=app.modules.authorization --cov=app.modules.actors --cov=app.modules.projects --cov-report=term-missing)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
python3 -m unittest -v scripts.test_lightweight_agent_gates
git diff --check
```

Hosted `Backend / test` is mandatory before merge and must preserve the full
semantic lanes, API E2E, repository-wide 78 percent floor, and applicable
actor/authorization subsystem 90 percent floors. This child adds a protected
`app/modules/projects/*` 90 percent coverage report to that hosted gate. The
full suite and coverage run in GitHub Actions; local verification is limited to
the focused tests, lint, API contract, and deterministic repository checks.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Stop conditions

Stop if safe context derivation requires exposing raw grants or if either route
would retain token-role authority.
