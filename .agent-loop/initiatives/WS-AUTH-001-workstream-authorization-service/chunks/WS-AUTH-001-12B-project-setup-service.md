# Chunk Contract: WS-AUTH-001-12B — Fixed Project Setup Service Foundation

## Status and prerequisite

Proposed and inactive after 12A. This child provisions planned matrix facts and
must activate no action or Celery call path.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Provision one exact project-setup service identity and planned memberships for
`project.guide_sufficiency.run`, `project.submission_artifact_policy.derive`,
`project.post_submit_checker_policy.derive`, and `project.setup_run.update`.
Activate none of them here.

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
backend/app/modules/actors/repository.py
backend/app/modules/actors/service_identities.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/modules/authorization/service_actor_service.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/service.py
backend/app/modules/projects/setup_queue.py
backend/alembic/versions/<then-current-next>_project_setup_service.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

Human route activation, Celery cutover, any action activation, generic
setup-service authority, serialized prepared handles, ART/provider behavior,
checker execution, or review/contribution behavior.

## Acceptance criteria

- Immutable identity `workstream.project.setup` has exactly the four parent actions and
  no human/admin/project grants.
- All four memberships remain planned and unavailable; the existing Celery
  call graph is not switched in this foundation.
- Exact setup run, project, guide, snapshot, generation, effective policy, and
  pre-submit checker facts are locked/recomposed as applicable before consume.
- Wrong service/action/project/guide/snapshot/run/generation, stale output,
  replay, revocation, copied handle, and transaction/session mismatch deny
  before durable mutation or external continuation.
- The fabricated legacy setup actor remains unchanged until 12B2; this
  foundation makes no Celery call-graph or runtime-principal change.
- Matrix tests prove the identity has only these four actions and all-pairs
  cross-service denial. Later 12E/12F/12G own product action activation; 12B2
  alone owns the final Celery call-graph cutover and setup-run writes.
- Every changed authorization/project/setup-service module remains at least 90
  percent covered. Final pushed head SHA passes `Backend / test` and
  `Agent Gates`.

## Verification commands

Before start, freeze the exact isolated-runner command, coverage includes,
Ruff, migration round-trip, fixed-service all-pairs denial proof, stale docs,
links, and diff commands.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Fixed-service least privilege, zero activation, and exact future memberships.

## Stop conditions

Stop if a membership is not in the parent table, any action must activate, or
the identity needs generic/human authority.
