# Chunk Contract: WS-AUTH-001-12F — Submission Artifact Policy Mutation Cutover

## Status and prerequisite

Proposed and inactive after 12E.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Activate draft creation, agent derivation, draft update, and approval for the
exact submission-artifact policy lineage.

## Why this chunk exists

Approval creates effective and pre-submit checker policy state and needs a
separate provenance migration and final-chain revalidation.

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
backend/app/modules/projects/post_submit_policy.py
backend/app/modules/projects/setup_queue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/api/deps/authorization.py
backend/alembic/versions/<then-current-next>_submission_policy_authority.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

Post-submit checker behavior, submission intake, ART provider/extraction,
review/revision/retired-economic/contribution policy, or issuer-claim fallback.

## Acceptance criteria

- Actions bind exact project, draft guide, source snapshot, setup generation,
  draft policy, effective output, compiled pre-submit output, actor/link, and
  grant-or-service authority as applicable.
- Create/update/approve are human Project Manager only. The derive action also
  admits only `workstream.project.setup` through its closed matrix membership.
- Service derivation additionally locks and binds the active setup run, expected
  submission-policy step, task/correlation identity, project, guide, snapshot,
  generation, and stale-output digest. It records service profile, identity
  link, and static-matrix membership, never a fabricated matched grant.
- Agent derivation carries no handle across external work and persists only
  after fresh authority plus stale-output revalidation.
- Approval locks the complete current chain and records actor profile, identity
  link, matched grant, scope project, action, and bounded decision evidence
  atomically with effective/pre-submit state.
- Historical bootstrap provenance remains readable; upgrade/downgrade/re-upgrade
  does not rewrite it.
- Draft create/update, agent derivation, approval, effective output, and
  pre-submit compilation each record local actor/link/grant-or-service/scope/action and
  decision-event provenance. 12F owns these columns; 12G owns its separate
  post-submit provenance migration.
- Missing/wrong setup run, wrong setup step or task, direct public service
  invocation, cross-project/guide/snapshot/generation, replay, stale policy or
  output, concurrent approval, service or human revocation, wrong
  handle/session/transaction, and partial-flush failures deny with one or zero
  business effects as specified.
- Final pushed head SHA passes `Backend / test` and `Agent Gates`.

## Verification commands

Before start, freeze exact isolated-runner, seeded migration round-trip,
authorization/project 90% coverage, repository-wide 78% coverage baseline,
Ruff, API drill, stale-doc, link, and diff commands.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Exact policy chain, approval provenance, stale agent output, and atomicity.

## Stop conditions

Stop if policy records must be collapsed, historical provenance rewritten, or
submission/checker execution behavior changed.
