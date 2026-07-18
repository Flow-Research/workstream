# Chunk Contract: WS-AUTH-001-09E - Fixed Service Runtime Admission

## Goal

Admit verified, explicitly provisioned service subjects into a separate typed
authorization path that selects only the fixed service identity's exact static
ActionId row. This chunk activates no feature action.

## Risk

L1 / P1. Required reviewers: senior engineering, QA/test, security/auth,
product/ops, architecture, CI integrity, docs, reuse/dedup, and test delta.

## Prerequisites

- AUTH-09A's fixed service-identity field and static service-action matrix are
  merged;
- AUTH-09B controlled provisioning can create the exact service ActorProfile
  and one active identity link;
- AUTH-09C administrative reads plus AUTH-09D-A profile lifecycle and 09D-B
  identity-link lifecycle are merged;
- service lifecycle state is canonical and no feature service action is active
  merely because this chunk starts.

## Allowed files

```text
backend/app/api/deps/authorization.py
backend/app/modules/actors/**
backend/app/modules/authorization/**
backend/tests/test_actors.py
backend/tests/test_auth.py
backend/tests/test_authorization.py
backend/tests/test_api_controls.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-09E.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
human first-access provisioning for service subjects
AdminRoleGrant, ProjectRoleGrant, Contributor, or human self-profile authority
client-supplied service identity, ActionId, PermissionId, role, or matrix membership
dynamic service grants, shared catch-all service identity, or permission union
feature resource composition, lifecycle behavior, adapter I/O, or action activation
application startup failure solely because a provisionable service row is absent
```

## Admission contract

```text
verified service token
-> exact ActorIdentityLink by configured issuer and opaque subject
-> active service ActorProfile
-> immutable fixed service_identity
-> exact static service-action matrix row
-> typed service AuthorizationContext
-> canonical feature ResourceContext and guards recomposed from locked rows
-> authorization decision
```

Human and service contexts are structurally distinct. Service context includes
the closed `service_identity`; human context cannot carry one. The service
candidate evaluator is selected before any human grant lookup and cannot fall
through to administrative or project contributor candidates.

## Acceptance criteria

- Unknown, unprovisioned, mismatched, suspended, deactivated, or link-revoked
  service subjects deny without persistence or first-access creation.
- A service action outside the exact matrix row denies even when it maps to a
  PermissionId used by an allowed row.
- Planned actions remain unavailable. This chunk changes no feature action to
  active and attaches no ART, REV, CON, project, task, or checker call site.
- Sensitive mutation revalidation reloads and locks the exact link/profile,
  verifies unchanged `service_identity`, matrix membership, and active action,
  then evaluates a feature-composed canonical `ResourceContext` recomputed from
  locked rows before terminal state can commit. Request- or service-supplied
  resource facts remain untrusted hints and never become authority.
- Service callers never enter human self actions, AdminRoleGrant evaluation,
  ProjectRoleGrant evaluation, contributor candidates, or human rate controls.
- Missing provisioned rows deny the request but do not prevent startup or the
  Access Administrator provisioning path.
- Static matrix and admission parity reject missing/extra identities, rows,
  actions, changed mappings, and cross-service substitution.
- Tests prove every fixed artifact service is denied every other service's
  actions, a human cannot use service candidates, and a service cannot use
  human grants.
- Focused authorization/actor coverage remains at least 90 percent and the
  repository-wide coverage floor does not regress.

## Stop condition

Stop after merge and signed memory. Do not start AUTH-10 or activate any feature
action automatically.
