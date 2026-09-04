# Chunk Contract: WS-AUTH-001-12I - Unified Compilation Authorization Activation

Status: Implemented and internally reviewed on the bounded branch. Risk: L1.

## Goal

Activate exactly two already-planned actions around the hidden immutable
unified-compilation parent:

- `project.guide_compilation.request` for a covered Project Manager to request
  or recover one exact asynchronous compilation attempt; and
- `project.guide_compilation.execute` for only the fixed
  `workstream.project.setup` service to admit provider execution and persist one
  exact accepted result.

This chunk installs AUTH's production implementation of the merged
`ProjectGuideCompilationAuthorizationPort`. It does not make the hidden POL
compilation workflow live; WS-POL-003-03B owns product orchestration and
composition after this activation merges.

## Why this chunk exists

POL-03A merged immutable attempt/result custody and a deny-only public AUTH
port. It deliberately cannot dispatch a model call or persist a compilation
until AUTH proves current human request authority, independent fixed-service
execution authority, and fresh transaction-bound final persistence authority.
The external-I/O gap must retain one attempt and provider idempotency key while
carrying no prepared handle or database transaction across the provider call.

## Exact ownership and modular boundary

- AUTH owns action/permission registration, evaluator rules, prepared handles,
  decision evidence, fixed-service matrix membership, and the concrete port.
- PROJECTS/POL owns guide/setup/catalogue/attempt/result facts and every product
  row. AUTH receives only the immutable public facts already defined in
  `app.modules.authorization.api.project_guide_compilation`.
- The production implementation lives inside AUTH and imports no PROJECTS
  model, repository, service, schema, or private type.
- POL continues importing AUTH only through `app.modules.authorization.api`.
- This chunk adds no cross-module private edge. The AUTH-003 ledger delta is
  zero additions and zero removals; its validator remains authoritative.
- WS-POL-003-03B later wires the concrete AUTH port at the application
  composition boundary. This chunk does not add a route, execution handler, Celery task,
  product service, or alternate composition path.

## Exact authority model

### Human request/recovery

`project.guide_compilation.request` maps only to the permission with the same
identifier. `authorization.policy` adds that permission only to
`AdminRole.PROJECT_MANAGER`; it is not a ProjectRole permission and is not
inherited by another admin role. It requires an active human actor profile, the
exact active identity link used for authentication, and a current covered
Project Manager AdminRoleGrant for the exact project. A system-wide or
different-project grant, another admin role, another identity link, and every
service identity deny.

Preparation and consumption bind the complete
`ProjectGuideCompilationRequestFacts`: project, guide/version, source snapshot
and hash, setup run/generation, canonical input and guide-material hashes,
operation/request/idempotency UUIDs, both catalogue identities/versions/schema
versions/manifest hashes, agent identity/version, instruction version, and the
optional exact predecessor compilation. The request evidence resource is
exactly `project_guide_compilation_request`, its resource ID is the canonical
`operation_id`, and its selector is the exact project. Its canonical digest
binds the action/permission, actor profile, identity link, Project Manager
grant, and every request fact above. The public API may add only the
dependency-free request-digest helper required to share this canonical shape;
the frozen fact dataclasses and Protocol method shapes do not change.
Consumption records dispatch/recovery authority only; POL-03B will commit that
event atomically with reservation/recovery custody whose stored operation,
request, idempotency, and lineage values must match. It creates or mutates no
compilation product row in this chunk.

### Fixed-service execution

`project.guide_compilation.execute` maps only to the permission with the same
identifier. It is granted only by the static service matrix row for
`workstream.project.setup`. The service actor profile, its exact service
identity link, service identity registration, matrix row, action, and
permission must all be active/current. No human grant or admin role can satisfy
this action, and no other service can borrow it.

Preflight is a fresh non-durable authorization decision over every request fact
plus exact attempt and provider-idempotency UUID. It occurs before future
provider I/O and does not create a prepared handle that survives that I/O.

After accepted output exists, final preparation and consumption bind every
preflight fact plus the complete result and component hashes and the canonical
resource-context digest. The opaque handle is process-local, single-use,
non-dataclass, non-Pydantic, non-JSON, and bound to the exact actor/link/service,
action, facts, database session, transaction, and prepared generation. It is
never copied, reconstructed, persisted, logged, or placed in Celery.

## Transaction and evidence boundary

- Request consumption and its allowed authority evidence share the transaction
  that POL-03B will use for durable dispatch/recovery custody.
- Execute preflight ends before provider I/O. No transaction or prepared handle
  spans external I/O.
- Final execute consumption occurs in a newly opened transaction after POL has
  reloaded and locked the exact attempt and current lineage.
- The allowed final decision event commits atomically with the immutable
  compilation row and attempt transition in POL-03B.
- Rollback leaves no allowed evidence or protected product mutation.
- AUTH never receives raw guide text, provider output, canonical result JSON,
  paths, URLs, credentials, prompts, reasoning, or Celery payloads.

## Allowed files

```text
backend/app/modules/authorization/api/__init__.py
backend/app/modules/authorization/api/project_guide_compilation.py
backend/app/modules/authorization/admin_schemas.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/guide_compilation.py
backend/app/modules/authorization/domain/**
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/models.py
backend/app/modules/authorization/policy.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/repository.py
backend/app/modules/authorization/runtime.py
backend/app/modules/audit/schemas.py
backend/alembic/versions/0063_guide_compilation_authority.py
backend/tests/architecture/test_authorization_boundary.py
backend/tests/authorization/guide_compilation/**
backend/tests/authorization/__init__.py
backend/tests/test_audit.py
backend/tests/test_alembic.py
backend/tests/test_auth.py
backend/tests/test_authorization.py
backend/tests/conftest.py
backend/tests/projects/guide_compilation/test_migration_contract.py
backend/scripts/authorization_boundary.py
.ci/behavior-ownership/auth/**
.ci/behavior-ownership/partition.v1.json
backend/scripts/behavior_ownership.py
backend/tests/test_behavior_ownership.py
backend/scripts/run_test_lanes.py
backend/scripts/run_isolated_tests.py
backend/scripts/validate_test_lane_evidence.py
backend/tests/test_ci_test_lanes.py
backend/tests/test_isolated_database_runner.py
backend/tests/test_merge_test_lane_evidence.py
backend/tests/test_test_lane_evidence.py
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
.github/workflows/backend.yml
scripts/test_lightweight_agent_gates.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/operations_backend_testing.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/**
.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/STATUS.md
docs/roadmap_status.md
```

Edits to `authorization/api/project_guide_compilation.py` are limited to the
dependency-free request-resource digest helper described above; the public fact
fields and authorization Protocol method shapes are frozen.

The migration identifier `0063_guide_compilation_authority` is valid only while
`0062_guide_compilation` remains the sole head after the implementation branch
rebases on then-current `main`. Tests in the broad historical files above may
change only for exact catalogue, SQL parity, migration topology, and existing
fixture registration. New behavioral proof belongs in the focused package.
Workflow/lane/ownership files may change only to add the exact focused tests and
90-percent materially changed AUTH surface gate; no existing gate may weaken.

## Not allowed

- Compilation schema, repository, validator, result, attempt, agent adapter,
  prompt, provider call, setup orchestration, policy projection, or product
  mutation changes.
- A route, live execution handler, Celery dispatch, serialized handle, raw
  `AuthorizationContext` as durable authority, or transaction across I/O.
- ART, CHECKER, TASK, REV, CON, or COMP behavior.
- Broad compile/download/agent authority, human/service authority inheritance,
  admin bypass, dynamic service lookup, compatibility alias, fallback, second
  evaluator, second factory, or ART/POL-local authorization path.
- Activation of sufficiency, artifact-policy, pre-submit, post-submit,
  approval, effective-policy, setup-ledger, guide-activation, submission, or
  checker actions.
- New private AUTH imports by another module or any new general module-boundary
  debt edge.

## Acceptance criteria

- Typed catalogue, SQL constraints/registries, evaluator ownership, action to
  permission mapping, fixed-service matrix, runtime availability, and docs are
  exactly in parity for the two actions and no others.
- Migration 0063 preserves 0062's existing execute audit/permission token
  exactly once, adds the request permission/action/resource/evidence tokens
  exactly once, adds both typed catalogue rows, and activates exactly the two
  actions. Empty upgrade/downgrade/re-upgrade preserves one head and exact
  parity; downgrade refuses once request or execute authority evidence exists.
- Covered Project Manager request prepare/consume succeeds only for the exact
  active actor, link, grant, project, request identity, immutable lineage,
  catalogues, and agent/instruction identity.
- Fixed `workstream.project.setup` preflight and final prepare/consume succeed
  only for the exact active service profile/link/matrix row and complete facts.
- Human callers cannot execute; services cannot request; admin cannot
  substitute; the binding/guide-reader/other services cannot use either action.
- Revoked/inactive/replaced actor, link, grant, service registration, service
  matrix row, action, or permission denies.
- Cross-principal, cross-link, cross-action, cross-project, cross-guide,
  cross-snapshot, cross-setup-run/generation, cross-catalogue, cross-agent,
  cross-attempt, wrong provider key, stale predecessor, changed result/component
  hash, wrong resource digest, copied handle, replayed handle, wrong session,
  wrong transaction, rollback, and prepared-generation replacement all deny.
- AUTH-level denial records no allowed evidence and invokes no callback. Actual
  provider/product side-effect ordering is deferred to POL-03B's composed
  consumer proof because this activation chunk contains no product orchestration.
  Rollback records no allowed evidence.
- Request-handle replay denies and retains the first allowed event UUID. POL-03B's
  atomic operation/idempotency custody must ensure concurrently prepared request
  handles commit at most one product mutation and therefore at most one allowed
  event; AUTH does not create a second durable idempotency protocol. Execute
  preflight is stateless and may be reevaluated only against freshly loaded
  current authority. Final execute-handle replay denies and retains the first
  allowed event UUID. Concurrent final handles rely on POL-03B's unique attempt
  transition to commit at most one product mutation and allowed event. Copied
  handles always deny and create no event.
- Public API leak/reachability proof shows the AUTH API reaches no PROJECTS or
  private AUTH implementation, while the concrete adapter reaches no PROJECTS
  private module.
- AUTH-003 and general modular-boundary debt do not grow.
- The materially changed AUTH surface is at least 90-percent covered and the
  repository-wide hosted 78-percent floor remains unchanged.

## Verification commands

```text
cd backend && .venv/bin/python -m scripts.authorization_boundary validate --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md
cd backend && .venv/bin/python -m scripts.test_structure_boundary validate --policy ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_POLICY.md --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/behavior_ownership.py validate
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend backend/.venv/bin/python -m pytest -q -p pytest_asyncio.plugin backend/tests/architecture/test_authorization_boundary.py backend/tests/authorization/guide_compilation
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend backend/.venv/bin/python -m pytest -q -p pytest_asyncio.plugin -p pytest_cov.plugin backend/tests/test_authorization.py backend/tests/authorization/guide_compilation --cov=app.modules.authorization --cov-branch --cov-report=term-missing --cov-fail-under=90
PYTHONPATH=backend backend/.venv/bin/ruff check backend/app/modules/authorization backend/tests/authorization/guide_compilation backend/tests/architecture/test_authorization_boundary.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

Full semantic Backend lanes, repository coverage, accumulated subsystem
coverage, Agent Gates, and external review run on the exact pushed GitHub head.

## Required reviewers

- architecture
- security
- QA
- product/operations
- senior engineering
- CI integrity
- reuse/dedup
- test delta
- docs

## Human review focus

Review the separation between covered human request custody and independent
fixed-service execution, the two authorization points around provider I/O, the
complete result-bound final digest, process-local handle integrity, atomic
decision evidence, zero product activation, and zero private-edge growth.
