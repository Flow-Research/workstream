# Chunk Contract: WS-AUTH-001-12E — Guide Sufficiency Mutation Cutover

## Status and prerequisite

Proposed and inactive after 12D2.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Activate manual sufficiency creation, agent-run request, and warning
acknowledgement for the covered Project Manager.

## Why this chunk exists

Sufficiency report lineage and external-agent transaction boundaries differ
from guide metadata and policy approval.

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/projects/models.py
backend/app/modules/projects/authorization_reads.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/router.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/api/deps/authorization.py
backend/alembic/versions/<then-current-next>_guide_sufficiency_authority.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

ART extraction/materialization, agent prompt semantics, policy approval,
activation, checker execution, or token-role fallback.

## Acceptance criteria

- Every action binds exact project, draft guide, current source snapshot,
  setup generation, report where applicable, actor/link, and
  grant-or-service authority.
- Report creation and warning acknowledgement are human Project Manager only.
  `project.guide_sufficiency.run` also admits only the fixed
  `workstream.project.setup` service through its closed matrix membership; the
  service receives no other human action.
- Service execution additionally locks and binds the active setup run, expected
  sufficiency step, task/correlation identity, project, guide, snapshot,
  generation, and stale-output digest. It records service profile, identity
  link, and static-matrix membership, never a fabricated matched grant.
- No prepared handle crosses agent execution. Final persistence uses fresh
  authority and rejects stale/replaced source or generation output.
- Report creation, agent-derived output, and warning acknowledgement each record
  local actor/link/grant-or-service/scope/action and decision-event provenance; legacy
  bootstrap history remains nullable/readable and is not rewritten.
- Missing/wrong setup run, wrong setup step or task, direct public service
  invocation, cross-project/guide/snapshot/generation, replay, service or human
  revocation, stale output, wrong transaction/session, and concurrent duplicate
  effects fail closed.
- Changed authorization/project modules remain at least 90 percent covered and
  final pushed head SHA passes `Backend / test` and `Agent Gates`.

## Verification commands

Before start, freeze exact isolated-runner, migration round-trip, coverage,
agent rollback/stale-output, Ruff, API drill, stale-doc, link, and diff commands.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

External-agent boundary, exact snapshot/generation, and acknowledgement
provenance.

## Stop conditions

Stop if a handle crosses external work or extracted bytes/content authority is
required from AUTH-12.
