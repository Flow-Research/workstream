# Chunk Contract: WS-AUTH-001-12H — Guide Activation Cutover

## Status and prerequisite

Proposed and inactive after 12B2 and the owning CON clean cut removes the
retired guide-bound economic-policy dependency.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Activate only `project.guide.activate` after every prerequisite project policy
mutation family is locally authorized and provenance-complete.

## Why this chunk exists

Guide activation is the terminal, high-value transition that publishes one
exact immutable guide/policy bundle and must be reviewed independently.

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
backend/alembic/versions/<then-current-next>_guide_activation_authority.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

Policy derivation/approval semantics, ART provider behavior, ContributionPolicy
or award redesign, task/submission/review activation, or issuer-claim fallback.

## Acceptance criteria

- Entry requires 12B through 12G, 12B2, and 12D2 merged and no legacy project mutation
  authority remaining in the activation call graph.
- Final consume locks/revalidates exact project, draft guide, source snapshot
  and items, setup run/generation, sufficiency, submission/effective/pre-submit
  and post-submit policies, plus current review/revision records. Retired
  guide-bound economic policy is neither read nor required.
- Covered Project Manager authority, matched grant/scope, actor/link, action,
  request digest and transaction are evidenced atomically with activation.
- Stale/replaced/missing/cross-resource chain, concurrent activation, revoked
  authority, replay, copied/wrong handle, and wrong session/transaction deny
  before any state change.
- Exactly one active guide results; no compatibility authorization path remains.
- Activation records local actor/link/grant/scope/action and decision-event
  provenance; historical rows remain nullable/readable. Final pushed head SHA
  passes `Backend / test` and `Agent Gates`.

## Verification commands

Before start, freeze exact isolated-runner, seeded migration round-trip,
authorization/project 90% coverage, activation/concurrency, API drill, Ruff,
stale-doc, link, and diff commands.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Complete locked lineage, terminal transition atomicity, prerequisite-only
legacy policy reads, and absence of fallback authority.

## Stop conditions

Stop if any prerequisite mutation family is not locally cut over, the owning
CON clean cut has not removed the retired economic-policy dependency, or
activation requires changing contribution semantics.
