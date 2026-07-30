# Chunk Contract: WS-AUTH-001-12B — Fixed Project Setup Service Foundation

## Status and prerequisite

Implementation and required internal review are complete from merged 12A at
trusted main `64dd9c98`; hosted PR checks remain pending. This child registers
planned matrix facts and activates no action or Celery call path. Its exact
migration is `0042_project_setup_service` after
`0041_project_mutation_evidence`.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Register one exact project-setup service identity and planned memberships for
`project.guide_sufficiency.run`, `project.submission_artifact_policy.derive`,
`project.post_submit_checker_policy.derive`, and `project.setup_run.update`.
Activate none of them here. Registration makes the closed identity available
to the existing controlled service-actor provisioning route only after an
administrator supplies an exact issuer and subject; this chunk seeds no actor
profile or identity link.

## Why this chunk exists

Celery setup currently fabricates human authority. Human cutovers need a closed
service identity before later children activate each exact product action.

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/actors/models.py
backend/app/modules/actors/service_identities.py
backend/app/modules/actors/service_identity_migration.py
backend/app/modules/authorization/catalogue.py
backend/alembic/versions/0042_project_setup_service.py
backend/tests/test_actor_migration_tools.py
backend/tests/test_authorization.py
backend/tests/test_alembic.py
backend/tests/test_auth.py
backend/tests/conftest.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

Human route activation, Celery cutover, any action activation, generic
setup-service authority, serialized prepared handles, ART/provider behavior,
checker execution, or review/contribution behavior. Do not change
`authorization/kernel.py`, `authorization/prepared.py`,
`authorization/runtime.py`, `authorization/service_actor_service.py`, any
project module, the setup queue, or the current Celery setup worker module.

## Acceptance criteria

- Immutable identity `workstream.project.setup` is registered as the eighth
  closed service identity and has exactly the four parent actions. Static
  membership grants no human/admin/project role, and migration `0042` seeds no
  ActorProfile, ActorIdentityLink, admin grant, or project grant.
- All four memberships remain planned and unavailable; the existing Celery
  call graph is not switched in this foundation.
- Own-action attempts fail with `action_unavailable` before actor/resource
  locks, handle issuance, or allowed evidence. Every other fixed identity fails
  each of these four actions with `permission_not_granted`; the project-setup
  identity likewise fails every action owned by another fixed identity.
- Live lock/recomposition, final PREP consumption, stale-output, replay,
  revocation, copied-handle, session/transaction, and external-continuation
  proof remains owned by 12E, 12F, 12G, and 12B2 after their exact actions
  activate. This foundation proves those paths are unreachable while planned.
- The fabricated legacy setup actor remains unchanged until 12B2; this
  foundation makes no Celery call-graph or runtime-principal change.
- Matrix tests prove the identity has only these four actions and all-pairs
  cross-service denial. Later 12E/12F/12G own product action activation; 12B2
  alone owns the final Celery call-graph cutover and setup-run writes.
- The frozen revision-0023 seven-identity migration contract is not edited.
  Its operator mapping tool consumes that frozen contract rather than the live
  registry. `0042` alone expands the current database constraint, round-trips
  cleanly, and refuses downgrade while a project-setup ActorProfile exists.
- Specification and operations docs list the eighth identity and its exact
  four planned/unavailable actions while preserving explicitly historical
  seven-identity AUTH-09A wording.
- Every changed authorization/project/setup-service module remains at least 90
  percent covered. Final pushed head SHA passes `Backend / test` and
  `Agent Gates`.

## Verification commands

```bash
cd backend
install -d -m 700 .ci
.venv/bin/python -m ruff check \
  app/modules/actors/models.py \
  app/modules/actors/service_identities.py \
  app/modules/actors/service_identity_migration.py \
  app/modules/authorization/catalogue.py \
  alembic/versions/0042_project_setup_service.py \
  tests/test_actor_migration_tools.py tests/test_authorization.py \
  tests/test_alembic.py tests/test_auth.py tests/conftest.py
.venv/bin/python -m py_compile \
  app/modules/actors/models.py \
  app/modules/actors/service_identities.py \
  app/modules/actors/service_identity_migration.py \
  app/modules/authorization/catalogue.py \
  alembic/versions/0042_project_setup_service.py \
  tests/test_actor_migration_tools.py tests/test_authorization.py \
  tests/test_alembic.py tests/test_auth.py tests/conftest.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json .ci/auth12b.json --lane auth12b --timeout-seconds 1200 -- \
  .venv/bin/python -m pytest -p pytest_asyncio.plugin -p pytest_cov.plugin -q \
  tests/test_actor_migration_tools.py tests/test_authorization.py tests/test_alembic.py \
  tests/test_auth.py \
  -k 'project_setup_service or controlled_service_actor_provisioning_includes_project_setup or fixed_service_action_matrix or 0042_project_setup or service_identity_migration_contract'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json .ci/auth12b-migration-coverage.json \
  --lane auth12b_migration_coverage --timeout-seconds 1200 -- sh -c \
  '.venv/bin/coverage erase && \
  .venv/bin/coverage run --include="*/alembic/versions/0042_project_setup_service.py" \
  -m pytest -p pytest_asyncio.plugin -q tests/test_alembic.py \
  -k "0042_project_setup" && \
  .venv/bin/coverage report \
  --include="*/alembic/versions/0042_project_setup_service.py" \
  --show-missing --fail-under=90'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  -p pytest_asyncio.plugin -p pytest_cov.plugin -q tests/test_actor_migration_tools.py \
  --cov=app.modules.actors.service_identity_migration \
  --cov-report=term-missing --cov-fail-under=90
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  -p pytest_asyncio.plugin -p pytest_cov.plugin -q tests/test_authorization.py \
  -k 'project_setup_service or fixed_service_action_matrix' \
  --cov=app.modules.actors.service_identities \
  --cov=app.modules.actors.models \
  --cov=app.modules.authorization.catalogue \
  --cov-report=term-missing --cov-fail-under=90
cd ..
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

Final pushed head SHA must pass `Backend / test` and `Agent Gates`; hosted
Backend owns fresh full-suite coverage and isolated PostgreSQL migration proof.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Fixed-service least privilege, zero activation, and exact future memberships.

## Stop conditions

Stop if a membership is not in the parent table, any action must activate, or
the identity needs generic/human authority.
