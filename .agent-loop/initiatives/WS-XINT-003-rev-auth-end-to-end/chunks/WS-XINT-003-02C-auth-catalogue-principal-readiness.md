# Chunk Contract: WS-XINT-003-02C — AUTH Catalogue And Principal Readiness

## Status

Proposed planning contract. Refresh exact migration head and verification
commands from current `main` before implementation.

## Parent initiative

`WS-XINT-003` — REV-AUTH End-to-End Contract.

## Goal

Install the complete approved v0.1 REV authorization catalogue, mappings,
fixed-service principals, and static service matrix once so REV implementation
cannot be interrupted by missing AUTH-owned values. Every review lifecycle
action remains unavailable.

## Why this chunk exists

The previous sequence deferred four ActionIds and six service identities until
late activation waves. REV therefore could not implement its lifecycle against
one stable AUTH surface. This chunk provides registration and admission without
granting execution authority.

## Risk class and SLA

L1 authorization catalogue, identity, and migration integrity. No expedited
review SLA.

## Allowed files

Refresh to exact current-main paths within:

```text
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/runtime.py
backend/app/modules/authorization/<bounded service identity modules>
backend/alembic/versions/<one new AUTH-owned migration>.py
backend/tests/<bounded authorization and migration tests>
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/operations_roles_permissions.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/**
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md
```

## Not allowed changes

- No REV queue, lease, finding, decision, revision, recovery, projection, or
  lifecycle implementation.
- No route, service job, provider I/O, action activation, or product release.
- No generic service principal or wildcard matrix membership.
- No compatibility aliases, duplicate permissions, dynamic service grants, or
  second authorization protocol.
- No XINT-002 action ownership or availability changes.

## Acceptance criteria

- All approved v0.1 `review.*` ActionIds in `ACTION_CUSTODY.md`, including the
  four formerly deferred recovery/lifecycle actions, exist exactly once in code
  and database parity and remain planned/unavailable.
- Existing PermissionIds are reused exactly as recorded; no PermissionId is
  added unless this plan is amended and reviewed again.
- The six exact REV fixed-service identities are closed registry values,
  provisionable through the canonical service-actor path, and mapped only to
  their recorded actions.
- The two identities sharing `review.reconcile.run` retain separate admitted
  identities and server-derived modes even though availability is global.
- Humans cannot use service actions; services cannot use human actions; every
  cross-service/action pair denies.
- Catalogue, migration, runtime owner, activation custody, static matrix, and
  service provisioning parity tests pass.
- Registration/provisioning produces no usable lifecycle authority while the
  action is unavailable.
- Migration upgrade/downgrade preserves exact parity and does not weaken any
  existing ART/AUTH or project authorization row.
- `review.finding_evidence.ingest` and
  `review.finding_response_evidence.ingest` receive an explicit
  future-intent-required unavailable classification (or an equivalently closed
  catalogue invariant) that ordinary v0.1 activation cannot select.

## Verification commands

Refresh exact paths at implementation start, then include Ruff, focused unit
and PostgreSQL catalogue/migration/service-matrix tests, changed-subsystem
coverage at or above 90 percent, and hosted Backend coverage preserving the
repository-wide 78 percent floor.

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
test delta, reuse/dedup, and docs.

## Human review focus

Confirm that the list is complete once, every service is least-privileged, and
nothing became available merely because it was registered or provisioned.

## Stop conditions

Stop on any new action/permission/principal requirement, uncertain migration
custody, or evidence that provisioning makes an unavailable action executable.
Merge this chunk and stop before 02D.
