# Chunk Contract: WS-AUTH-001-12D2 — Review And Revision Policy Mutation Separation

## Status and prerequisite

Proposed and inactive after 12D.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Add separately authorized routes for review and revision policy records after
12D alone removes the embedded guide create/update fields.

## Why this chunk exists

Guide management must not imply review/revision-policy authority. Retired
guide-bound economic policy remains CON-owned and has no AUTH-12 replacement.

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/projects/models.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/router.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/app/modules/projects/authorization_reads.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/api/deps/authorization.py
backend/alembic/versions/<then-current-next>_review_revision_policy_authority.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

Review execution/decision lifecycle, ContributionPolicy or award semantics,
fulfillment, guide metadata, submission/checker behavior, ART, or issuer-claim
compatibility.

## Acceptance criteria

- `project.review_policy.update` and `project.revision_policy.update` require
  an exact-project Project Manager grant with `project.review_policy.manage`.
- Entry requires merged 12D. 12D2 does not edit the removed guide payload fields
  or restore any compatibility alias.
- Each route locks the exact project, draft guide/version, current policy row,
  actor/link/grant/scope, consumes PREP once, and commits policy plus bounded
  decision evidence and provenance atomically.
- Each new/updated row records local actor profile, identity link, matched grant,
  project scope, action, and decision-event reference. Historical rows remain
  nullable/readable and are not rewritten.
- UUID idempotency, concealed 404 project-resource denials, canonical conflict,
  denial-evidence restaging, replay, revocation, cross-guide/project, stale row,
  and concurrency follow the parent invariants.
- OpenAPI declares exactly one primary action per new route and no compatibility
  endpoint is added.

## Verification commands

Before start, freeze exact isolated-runner, Ruff, migration round-trip,
changed-project/authorization 90% coverage, API drill, stale-doc, link, and diff
commands. Final pushed head SHA must pass `Backend / test` and `Agent Gates`.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Exact review/revision resources, hard API cut, provenance, and strict CON
economic-policy ownership.

## Stop conditions

Stop if retired economic-policy behavior reappears, behavior expands past
review/revision configuration, or historical rows must be rewritten.
