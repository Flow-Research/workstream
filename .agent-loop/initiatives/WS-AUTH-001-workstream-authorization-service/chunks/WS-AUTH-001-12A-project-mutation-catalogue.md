# Chunk Contract: WS-AUTH-001-12A — Project Mutation Catalogue And PREP Foundation

## Status and prerequisite

Proposed and inactive. AUTH-12 planning must be merged; ART-owned `0040` is
merged on trusted main.
the exact AUTH migration revision is frozen from the resulting trusted main.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Register the parent inventory's eighteen exact actions as planned, define their
typed resource/PREP contracts, and establish typed/PostgreSQL evidence parity
without activating a route or setup-service command.

## Why this chunk exists

Runtime children must not invent actions, generic policy resources, or lock
orders while cutting over sensitive mutations.

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/runtime.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/audit/schemas.py
backend/alembic/versions/<next-after-merged-ART-0040>_project_mutation_action_evidence.py
backend/tests/test_authorization.py
backend/tests/test_alembic.py
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

Action activation, route/service/worker behavior, service provisioning,
project-table provenance columns, ART behavior, or token-role compatibility.

## Acceptance criteria

- The exact eighteen-row parent inventory has closed typed and PostgreSQL
  ActionId/PermissionId/owner parity and remains planned.
- Exact ActionOwner values are `WS-AUTH-001-12C`, `WS-AUTH-001-12B2`,
  `WS-AUTH-001-12D`, `WS-AUTH-001-12D2`, `WS-AUTH-001-12E`,
  `WS-AUTH-001-12F`, `WS-AUTH-001-12G`, and `WS-AUTH-001-12H` as assigned by
  the parent table; no parent or feature owner is accepted.
- Resource contexts preserve separate project, guide, source snapshot,
  sufficiency report, submission policy, checker policy, setup run, and active
  bundle identities; no generic policy context exists.
- PREP scope derivation is explicit for system project creation and exact
  project resources. Handles remain opaque, request/session/transaction bound,
  non-copyable, non-serializable, and single-use.
- The migration follows merged ART-owned `0040_guide_materialization`; `0040`
  is not duplicated or edited.
- Upgrade, downgrade, re-upgrade, typed/SQL parity, and zero-active-delta tests
  pass.

## Verification commands

Before start, freeze the actual revision after merged ART `0040` and the exact
isolated-runner, 90% authorization coverage, migration round-trip, Ruff, stale
authorization docs, Markdown-link, and diff commands. Final pushed head SHA
must pass `Backend / test` and `Agent Gates`.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Exact inventory parity, typed resource separation, PREP scope, zero activation,
and migration custody.

## Stop conditions

Stop if ART `0040` is not merged before migration allocation, any action or
resource changes from the parent inventory, or runtime activation is required.
