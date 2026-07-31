# Chunk Contract: WS-AUTH-001-12C — Project Creation Cutover

## Status and prerequisite

Ready for pre-implementation review from merged main `57c67116`, after 12B.
The exact migration is `0044_project_create_authority` after merged migration
`0043_project_setup_service`.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Activate only `project.create` for a system-scoped Project Manager and remove
token-role authority from project-shell creation.

## Why this chunk exists

Project creation has system scope and cannot share the resource/lock semantics
of mutations against an existing project.

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/projects/models.py
backend/app/modules/projects/create_repository.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/router.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/modules/audit/schemas.py
backend/app/api/deps/authorization.py
backend/alembic/versions/0044_project_create_authority.py
.github/workflows/backend.yml
backend/tests/test_authorization.py
backend/tests/test_audit.py
backend/tests/test_projects.py
backend/tests/project_create_fixtures.py
backend/tests/test_artifact_admission.py
backend/tests/test_artifact_internal_authorization.py
backend/tests/test_artifact_recovery.py
backend/tests/test_guide_bindings.py
backend/tests/test_auth.py
backend/tests/test_alembic.py
backend/tests/test_api_controls.py
backend/tests/test_checkers.py
backend/tests/conftest.py
backend/tests/test_tasks.py
backend/tests/test_outbox.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

Guide/policy/setup/activation mutations, project update/archive invention,
project-scoped create authority, or token-role fallback.

## Acceptance criteria

- Only an active human with an active identity link and effective system-scoped
  Project Manager `project.create` grant may create a project.
- Project-scoped Project Manager, all contributor grants, and every other admin
  role deny. Every service actor, including `workstream.project.setup`, denies.
- PREP binds actor/link, system grant, request digest, idempotency key, root
  transaction, a distinct server-created operation identity, and server-created
  project identity; evidence, idempotency result, and project commit atomically
  once.
- The route generates or recovers the distinct stable operation and project
  UUIDs before PREP.
  Its canonical request value binds the exact action, route identity, validated
  body, actor profile, identity link, UUID idempotency key, operation UUID,
  project UUID, and operation generation before `prepare`; final consumption
  must reproduce those exact facts.
- `project.create` receives one narrow project-mutation branch in PREP. It must
  not be added to `_ADMIN_MUTATIONS`, the authority-mutation service, or any
  generic mutation branch. That branch locks and revalidates the active human,
  active link, and exact effective system-scoped Project Manager grant through
  final consumption; every other planned project mutation remains unavailable.
- Replay, copied/wrong handle, revoked authority, wrong session/transaction,
  and duplicate idempotency produce at most one project.
- The route declares exactly one active ActionId and contains no legacy coarse
  role-claim authorization helper.
- New project rows record local actor profile, identity link, matched grant,
  system scope, action, and decision-event reference; historical rows remain
  readable and are not rewritten.
- Project-owned idempotency records have a unique actor/action/key namespace,
  bind the canonical request digest and both server-owned identities, and return
  the original response only for an exact committed replay. A key reused with
  different request facts denies without creating a second project. This does
  not widen or modify `AuthorityIdempotencyRecord`, `AuthorityMutationService`,
  or the closed authority-operation types; persistence stays in the projects
  module and migration.
- The project persistence surface is `ProjectCreateIdempotencyRecord` in the
  projects model/repository. It stores actor profile, identity link, action,
  UUID key, canonical client-request digest, server operation UUID, server
  project UUID, generation, and `pending|committed` state. Reservation inserts
  or locks this row first; an exact existing row supplies the stable server IDs
  used by PREP, mismatch conflicts, and only a committed row may replay the
  original Project response. Completion changes `pending` to `committed` in the
  same root transaction as project/evidence insertion; rollback removes the
  reservation and no pending record may survive a failed request.
- New `Project` provenance columns are nullable only for historical rows:
  `created_by_actor_profile_id`, `created_via_identity_link_id`,
  `created_by_admin_role_grant_id`, `creation_scope_type`,
  `creation_action_id`, and `authorization_decision_event_id`. Foreign keys and
  a complete-or-empty check require new authorized rows to carry the exact
  actor/link/grant, literal `system` scope, literal `project.create` action, and
  allowed decision event. These internal fields are not added to public project
  responses.
- Missing or malformed `Idempotency-Key` denies before mutation. Exact committed
  replay returns the original 201 response; mismatched reuse returns the
  canonical `idempotency_mismatch` conflict. Concurrent exact replay creates one
  project, while concurrent mismatched reuse, copied keys across actors/links,
  different keys racing on one slug, and failures after reservation leave no
  duplicate project, false allowed evidence, or stuck pending record.
- Exact committed replay is response recovery, not a second authorization or
  mutation. It validates the actor/action/key/request-digest namespace and the
  database-enforced committed custody chain, then returns the original response
  without PREP, new allowed evidence, or dependence on authority revoked after
  the original commit. Revocation still denies every new key or changed request.
- Allowed decision evidence includes the canonical project-create resource
  digest and the operation/project identifiers. Database tests tie that event,
  the project provenance, and the idempotency row to the same facts.
- Migration `0044` preserves historical project rows through nullable
  provenance, enforces actor/link/grant/action/system-scope/decision references
  for newly authorized rows, enforces the replay namespace and digest/identity
  shape, and refuses downgrade once 12C provenance or replay data exists.
- OpenAPI declares exactly `project.create` for `POST /projects`; static/API
  tests prove the route and service contain no token-role or legacy coarse-role
  helper fallback.
- A successful call creates only the draft project shell and its authorization
  provenance/replay evidence. It creates no guide, source, setup run, task,
  submission, checker, review, revision, contribution, compensation award or
  fulfillment, reputation signal, policy, or activation state; denial/replay
  tests assert those downstream tables remain untouched.
- The ordered mutation is: validate body/header and resolve the local actor;
  reserve or lock project-owned idempotency and obtain stable operation/project
  IDs; prepare the exact system authority; consume it against final server
  facts; insert project with provenance; mark replay state committed; commit
  once in the route-owned root transaction. `ProjectService.create_project`
  must neither authorize from token roles nor commit independently.
- Every changed authorization/project module remains at least 90 percent
  covered. Final pushed head SHA passes `Backend / test` and `Agent Gates`.

## Verification commands

```bash
cd backend
install -d -m 700 .ci
: "${WORKSTREAM_TEST_ADMIN_DATABASE_URL:?set a local Postgres admin URL}"
.venv/bin/python -m ruff check \
  app/modules/projects/models.py app/modules/projects/repository.py \
  app/modules/projects/router.py app/modules/projects/schemas.py \
  app/modules/projects/service.py app/modules/authorization/catalogue.py \
  app/modules/authorization/kernel.py app/modules/authorization/prepared.py \
  app/modules/authorization/runtime.py app/api/deps/authorization.py \
  app/modules/audit/schemas.py \
  alembic/versions/0044_project_create_authority.py \
  tests/test_authorization.py tests/test_projects.py tests/test_alembic.py \
  tests/test_api_controls.py tests/conftest.py scripts/api_contract_e2e.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json .ci/auth12c.json --lane auth12c --timeout-seconds 1200 -- \
  .venv/bin/python -m pytest -p pytest_asyncio.plugin -p pytest_cov.plugin -q \
  tests/test_authorization.py tests/test_projects.py tests/test_alembic.py \
  tests/test_api_controls.py -k 'project_create or 0044_project_create'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json .ci/auth12c-coverage.json --lane auth12c_coverage \
  --timeout-seconds 1200 -- sh -c \
  '.venv/bin/coverage erase && .venv/bin/coverage run \
  --source=app.modules.projects,app.modules.authorization,app.modules.audit \
  -m pytest -p pytest_asyncio.plugin -q tests/test_authorization.py \
  tests/test_projects.py -k "project_create" && .venv/bin/coverage report \
  --include="*/app/modules/projects/*,*/app/modules/authorization/*,*/app/modules/audit/*" \
  --show-missing --fail-under=90'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json .ci/auth12c-api.json --lane auth12c_api \
  --timeout-seconds 1500 -- .venv/bin/python scripts/api_contract_e2e.py
cd ..
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

Final pushed head SHA must pass `Backend / test` and `Agent Gates`; hosted
Backend owns fresh full-suite coverage and isolated PostgreSQL migration proof.
The trust bundle must also show each changed backend module at or above 90
percent; aggregate package coverage cannot conceal a changed file below the
threshold. Hosted Backend adds a per-file 90-percent gate for the changed
project-create modules using the combined full-suite coverage artifact; the
Ruff, test, or coverage gate may not be weakened.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

System scope, creation idempotency, transaction ownership, and denial matrix.

## Stop conditions

Stop if project identity cannot be server-owned or project-scoped authority can
create a project.
