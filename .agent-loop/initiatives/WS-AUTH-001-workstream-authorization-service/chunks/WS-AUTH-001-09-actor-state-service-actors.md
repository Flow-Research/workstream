# Chunk Contract: WS-AUTH-001-09 - Actor State, Identity Revocation, And Service Actors

## Status

Superseded as an executable chunk by `WS-AUTH-001-09A` through
`WS-AUTH-001-09E`. This file records parent scope only; no runtime work or merge
intent may execute against `WS-AUTH-001-09`.

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Bound the actor/link/service scope that is implemented only through the reviewed
`09A` through `09E` child contracts.

## Why this chunk exists

Local role grants are incomplete without immediate actor/link invalidation and
controlled service identity resolution. The parent was too broad for one L1
implementation and was split before runtime work.

## Child ownership

- `09A`: fixed service identity and typed static service-action matrix.
- `09B`: controlled service ActorProfile/ActorIdentityLink provisioning.
- `09C`: actor and identity-link administrative reads.
- `09D`: actor and identity-link lifecycle mutations.
- `09E`: fixed service runtime admission without feature action activation.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/actors/**
backend/app/modules/authorization/**
backend/app/api/router.py
backend/app/modules/audit/**
backend/tests/test_actors.py
backend/tests/test_auth.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/operations_authorization_service.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
service actors receiving Contributor domain, AdminRoleGrant, or ProjectRoleGrant
deactivation reversal
deleting actors, links, grants, or historical attribution
product adapter bindings or callback endpoints
```

## Acceptance criteria

- Suspension blocks later business mutations and is reversible.
- Deactivation is terminal and preserves history.
- Identity-link revocation blocks the same issuer subject immediately; link
  reactivation restores the same profile without duplication.
- Identity-link revocation for an effective Access Administrator takes the same
  `AuthorityControl FOR UPDATE` lock as grant/profile removal.
- Self-suspension/deactivation and final-admin loss are denied under the shared
  authority lock.
- Unknown services are denied without persistence.
- Access Administrator can pre-provision a service profile/link with reason.
- Artifact system principals are fixed service identities, never human/admin
  grants. Their eventual permissions are drawn only from the closed registry.
  This chunk provisions the identities but does not attach them to artifact
  call sites or activate them. Each owning WS-ART chunk later supplies hidden
  resource facts, guards, surfaces, decision calls, behavior, and tests. The
  dedicated AUTH custodian alone integrates the evaluator and changes the exact
  action to active afterward.
- The artifact service-principal allowlist is limited to
  `artifact.verification.execute`, `artifact.pending_work.scan`,
  `artifact.put_attempt.resolve`, `artifact.upload_session.expire`,
  `artifact.binding.create`, `artifact.guide_source.read`,
  `artifact.checker_input.materialize`, and `artifact.checker_output.write`.
  Operator reads/retry and contributor ingest/upload actions are excluded.
- The fixed identities are `workstream.artifact.verifier`,
  `workstream.artifact.put_resolver`, `workstream.artifact.scheduler`,
  `workstream.artifact.binding`, `workstream.artifact.guide_reader`,
  `workstream.artifact.materializer`, and
  `workstream.artifact.checker_output`. Their exact static ActionId matrix rows
  are closed in `docs/spec_authorization_service.md`; no principal receives the
  union of the allowlist.
- AUTH-09A defines only exact registered ActionId matrix membership from that
  table. Generic
  PermissionIds such as `artifact.binding.create` and
  `artifact.checker_input.materialize` are never executable action names and
  are never granted as an implicit union of their mapped actions. A planned
  matrix row remains inert while ART builds the action's hidden canonical
  resource composer, guards, surface, and behavior proof, and until the later
  AUTH activation checkpoint integrates its evaluator and changes availability.
- Startup parity tests fail closed when any fixed artifact service actor,
  identity link, action registration, PermissionId mapping, or exact static
  matrix membership is missing or extra. Negative tests prove each identity is
  denied all artifact actions outside its matrix row.
- Agent and Space subjects remain unsupported and unpersisted.
- Every mutation is idempotent, reasoned, and audited without token material.
- Mixed concurrent link-revoke, grant-revoke, suspend, and deactivate attempts
  leave at least one authenticatable effective Access Administrator.
- `GET /api/v1/admin/actors`, actor detail, suspend/reactivate/deactivate,
  actor identity-link read, identity-link revoke/reactivate, and service actor
  create/list/detail routes from the adopted contract have
  allow/deny/privacy/rate-limit/replay tests.
- Every protected actor/link/service route declares one active `ActionId` mapped
  to the existing actor profile, identity-link, or service-provision permission
  and its canonically loaded target. Generated manifest-delta tests prove every
  surface introduced here has exactly one declaration.
- Suspension/link-revocation events explicitly require consuming lifecycle
  reconciliation; task assignment consumption belongs to chunk 13 and review
  lease consumption remains deferred to WS-REV-001.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q \
  tests/test_authorization.py tests/test_auth.py tests/test_actors.py \
  --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Review state-machine terminality, service separation, invalidation timing, and
preservation of historical records.

## Stop conditions

Stop if a consuming adapter authority must be invented or if a service must be
treated as a human/admin to make tests pass.
