# Chunk Contract: WS-ARCH-001-CP03B — Adapter-Binding AUTH Activation

## Merge state

- Outcome on merge: `complete`
- Implementation outcome: complete.

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Install the AUTH-owned adapter for CP02's hidden adapter-binding service and
activate exactly the existing read, create, suspend, and resume actions for a
human Finance Authority covering the exact project.

## Why this chunk exists

CP01A/CP01C registered exact immutable authorization facts while leaving the
four actions unavailable. CP02 then proved the route-unreachable CON lifecycle,
owner fences, transaction custody, idempotent recovery, and deny-default
composition. CP03A registers the exact compensation-adapter target identity and
installs real PROJECTS/ACTORS owner adapters. CP03B is the narrow activation
boundary: AUTH may now authorize
those proven operations without granting generic compensation authority or
moving CON behavior into AUTH.

## Approved plan references

- INTENT: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md`
- CP02 contract: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP02-con-binding-behavior.md`
- CON handoff: `.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/AUTHORIZATION_HANDOFF.md`

## Risk class

L1 — authorization and compensation infrastructure activation.

## SLA

P1

## Entry gate

- CP01A and CP01C are merged with the exact four action identifiers, permission
  mapping, typed facts, and canonical resource digests.
- CP02 is merged with hidden CON create/read/suspend/resume behavior, immutable
  lifecycle history, owner-held eligibility fences, operation fencing, and
  deny-default production composition.
- CP03A is merged with the exact target identity, owner adapters, and migration
  head recorded by that chunk. CP03B adds no migration.
- No public adapter-binding route exists. CP03 does not add one.

## Exact activation manifest

| ActionId | PermissionId | Principal | Protocol | Exact resource |
|---|---|---|---|---|
| `compensation.adapter_binding.read` | `compensation.adapter_binding.manage` | active human Finance Authority covering the exact project | request-scoped query authorization | `project_id`, `adapter_binding_id` |
| `compensation.adapter_binding.create` | `compensation.adapter_binding.manage` | active human Finance Authority covering the exact project | opaque transaction-bound PREP | project, server-generated binding identity, `instrument_type`, eligible adapter actor, non-secret route key, operation and request digest |
| `compensation.adapter_binding.suspend` | `compensation.adapter_binding.manage` | active human Finance Authority covering the exact project | opaque transaction-bound PREP | project, exact active binding, expected lifecycle version, operation and request digest |
| `compensation.adapter_binding.resume` | `compensation.adapter_binding.manage` | active human Finance Authority covering the exact project | opaque transaction-bound PREP | project, exact suspended binding, expected lifecycle version, operation and request digest |

System-scoped Finance Authority covers every eligible project; project-scoped
Finance Authority covers only its exact project. No other administrative role,
project role, service identity, or database principal may substitute.

## Required authorization composition

### Query

`read` resolves the authenticated human ActorProfile and exact active identity
link, uses canonical owner facts for the exact project/binding, verifies one
effective Finance Authority grant covering the project, and evaluates the
active read action against the exact CP01C resource digest. Missing, stale,
cross-project, revoked, wrong-kind, or unauthorized targets use CP02's single
concealed conflict behavior.

Exact duplicate mutation recovery performs this fresh read authorization. It
creates no mutation PREP, mutation-allowed evidence, binding change, lifecycle
event, or product effect. Query-scoped read-decision evidence may be staged for
the recovered binding but cannot be used as mutation authority.

### Mutation

The adapter translates CP02's public immutable mutation facts into the existing
AUTH public PREP protocol. The prepared handle remains opaque, process-local,
non-serializable, single-use, actor-bound, identity-link-bound, action-bound,
permission-bound, resource-digest-bound, operation-bound, request-digest-bound,
session-bound, and transaction-bound.

CP02 retains its mandatory ordering:

```text
root transaction
-> canonical request digest
-> PostgreSQL operation fence and recovery check
-> PROJECTS then ACTORS eligibility fences where required
-> binding row lock where required
-> AUTH prepare
-> AUTH consume
-> AUTH close in finally
-> CON mutation and immutable lifecycle event
-> flush
-> caller commits once
```

AUTH returns the exact authorized `actor_profile_id`; CP02 rejects any mismatch.
AUTH evidence and the CON mutation commit or roll back together. AUTH does not
commit, construct product rows, acquire CON locks, or import CON models or
repositories.

## Allowed files

```text
backend/app/modules/authorization/api/adapter_bindings.py
backend/app/modules/authorization/api/__init__.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/runtime.py (closed resource-context union only)
backend/app/modules/audit/schemas.py (register the exact `compensation_adapter_binding`
  audit resource type only)
backend/app/modules/authorization/prepared.py (reuse/integration only)
backend/app/modules/authorization/kernel.py (exact Finance Authority evaluator integration only)
backend/app/modules/authorization/adapter_binding_authorization.py
backend/app/modules/authorization/domain/adapter_bindings.py
backend/app/modules/authorization/domain/prepared_adapter_bindings.py
backend/app/adapters/auth/adapter_bindings.py (public AUTH API consumption only;
  no private AUTH implementation import)
backend/app/adapters/auth/__init__.py (exact AUTH adapter-root composition;
  same-owner private wiring is permitted only here)
backend/app/api/deps/authorization.py (composition only; no route)
backend/app/main.py (composition only; no route)
backend/app/modules/compensation/api/adapter_bindings.py (public-port parity only)
backend/app/modules/compensation/service.py (dependency injection only; no lifecycle behavior change)
backend/tests/authorization/test_adapter_binding_registration.py
backend/tests/authorization/test_adapter_binding_authorization.py
backend/tests/compensation/test_adapter_binding_authorization_integration.py
backend/tests/compensation/test_adapter_binding_authorization_failures.py
backend/tests/compensation/test_adapter_binding_recovery.py
backend/tests/compensation/test_adapter_binding_owner_fences.py
backend/tests/compensation/test_adapter_binding_service.py
backend/tests/compensation/test_adapter_binding_database_guards.py
backend/tests/compensation/test_adapter_binding_persistence.py
backend/tests/architecture/test_authorization_boundary.py
backend/scripts/authorization_boundary.py (exact AUTH adapter-root ownership only)
backend/scripts/module_boundaries.py (AUTH adapter-root parity only; no general adapter exception)
backend/tests/architecture/test_module_boundaries.py (repository-wide AUTH-view parity proof only)
backend/tests/test_authorization.py (closed catalogue/evaluator parity only)
backend/tests/test_audit.py (atomic evidence parity only)
backend/scripts/behavior_ownership.py (exact changed-target ownership only)
backend/scripts/run_test_lanes.py (exact CP03 test custody only)
.ci/behavior-ownership/partition.v1.json (exact additive target parity only)
.ci/behavior-ownership/auth/adapter-binding-activation.json
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json (generated parity only)
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/STATUS.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP03-auth-binding-activation.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP03A-owner-eligibility.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP03B-auth-binding-activation.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP03B-plan-review-evidence.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP03B-implementation-review-evidence.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP03B-external-review-response.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP03B-pr-trust-bundle.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/STATUS.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/AUTHORIZATION_HANDOFF.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/CHUNK_MAP.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/STATUS.md
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/spec_contribution_compensation.md
docs/roadmap_status.md
```

If implementation proves another file is essential, stop and amend/re-review
this contract before touching it. The named review paths do not authorize
arbitrary initiative files.

## Not allowed

```text
public HTTP routes or frontend behavior
new ActionId, PermissionId, role, service identity, matrix row, or database grant
database migration or schema change
ContributionPolicy behavior or activation
adapter-binding retirement
award, fulfillment, callback, dispatcher, delivery, reconciliation, or provider behavior
CON model, repository, lifecycle, operation-fence, owner-fence, or idempotency changes
AUTH imports of CON private modules, models, repositories, or services
CON imports of AUTH private modules
raw AuthorizationContext as durable mutation authority
another prepared-authorization protocol, generic resource dictionary, compatibility alias, fallback evaluator, or dual composition path
Project Manager, Operator, Access Administrator, Audit Authority, project-role, or service substitution for Finance Authority
```

## Acceptance criteria

- [x] Exactly the four manifest actions become `ACTIVE`, remain mapped only to
      `compensation.adapter_binding.manage`, and retain their existing owner.
- [x] The active catalogue count increases by exactly four; every adjacent
      ContributionPolicy, retirement, award, fulfillment, callback, delivery,
      dispatcher, and reconciliation action remains unavailable or absent.
- [x] Only an active human profile with the exact active identity link and an
      effective system- or same-project `finance_authority` grant can read or
      mutate a binding in that covered project.
- [x] Project Manager, Operator, Access Administrator, Audit Authority,
      Submitter, Reviewer, Adjudicator, fixed services, unrelated services,
      wrong-project Finance Authority, revoked/inactive profiles or links, and
      revoked/stale grants deny without target disclosure.
- [x] Read authorization binds the exact project and binding identity.
- [x] Create PREP binds actor, link, action, permission, project, generated
      binding ID, `instrument_type`, adapter actor, route key, operation,
      request digest, resource digest, session, and transaction.
- [x] Suspend/resume PREP additionally binds the exact expected status and
      positive lifecycle version. Wrong action/status/version/resource,
      copied handle, replay, wrong session, wrong transaction, replaced root
      transaction, or mutated facts deny.
- [x] Every prepared object closes exactly once on success, denial, conflict,
      exception, and rollback; no handle can be serialized or reused.
- [x] AUTH evidence commits atomically with the exact CP02 binding/lifecycle
      event. Denial or downstream failure leaves no binding change, lifecycle
      event, or allowed evidence.
- [x] Exact duplicate recovery uses fresh read authority and produces the
      immutable original result without a second mutation PREP or mutation
      evidence effect; any read evidence remains query-only, and changed facts
      or denied current read remain concealed.
- [x] CP02's PROJECTS-then-ACTORS eligibility fences and operation ordering
      remain intact for create/resume, including revocation races.
- [x] The AUTH application composition root exposes one real adapter factory
      through public ports. This chunk intentionally creates no route or
      reachable internal command caller; any future caller must explicitly
      inject that factory. CP02's safe deny-default constructor remains for
      uncomposed/isolated use. This is not compensation delivery, fulfillment,
      callback, or provider behavior.
- [x] Both authorization boundary scanners treat only
      `backend/app/adapters/auth/__init__.py` as AUTH-owned composition for
      same-owner private AUTH wiring; nested auth adapter files remain external
      consumers restricted to `authorization.api`, and root imports of
      non-AUTH private modules remain AUTH outbound debt.
- [x] No public route becomes reachable and no migration is added.
- [x] AUTH and changed compensation authorization coverage remain at or above
      90 percent; repository coverage remains at or above the protected floor.

## Required focused proof

### Positive

- system Finance Authority read/create/suspend/resume;
- exact-project Finance Authority read/create/suspend/resume;
- one lifecycle event and one allowed evidence effect per successful mutation;
- exact duplicate recovery with fresh authorized read and no second mutation
  effect.

### Principal and scope isolation

- every excluded administrative/project/service principal denies;
- wrong-project, revoked/inactive profile or link, revoked/stale grant,
  non-human context, and mismatched authenticated actor deny;
- system scope does not bypass resource lifecycle or owner eligibility.

### PREP and resource integrity

- wrong action, permission, project, binding, instrument, adapter actor, route,
  operation, request digest, expected status/version, session, transaction, and
  replaced transaction deny;
- copied, reconstructed, serialized, closed, and replayed handles deny;
- returned-actor mismatch denies before CON mutation.

### Atomicity and ordering

- AUTH consumes before binding mutation/lifecycle-event staging;
- consume denial/exception, close failure, wrong actor, CON flush failure, and
  transaction rollback leave zero product and allowed-evidence effects;
- create/resume owner locks remain held through AUTH and mutation;
- concurrent same-operation recovery and distinct-operation one-active-binding
  behavior remain unchanged.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/audit/schemas.py app/modules/authorization/api/adapter_bindings.py app/modules/authorization/api/__init__.py app/modules/authorization/catalogue.py app/modules/authorization/runtime.py app/modules/authorization/prepared.py app/modules/authorization/kernel.py app/modules/authorization/domain/adapter_bindings.py app/modules/authorization/domain/prepared_adapter_bindings.py app/modules/authorization/adapter_binding_authorization.py app/adapters/auth/adapter_bindings.py app/adapters/auth/__init__.py app/api/deps/authorization.py app/main.py app/modules/compensation/api/adapter_bindings.py app/modules/compensation/service.py tests/authorization/test_adapter_binding_registration.py tests/authorization/test_adapter_binding_authorization.py tests/compensation/test_adapter_binding_authorization_integration.py tests/compensation/test_adapter_binding_authorization_failures.py tests/compensation/test_adapter_binding_recovery.py tests/compensation/test_adapter_binding_owner_fences.py tests/compensation/test_adapter_binding_service.py tests/compensation/test_adapter_binding_database_guards.py tests/compensation/test_adapter_binding_persistence.py tests/architecture/test_authorization_boundary.py tests/architecture/test_module_boundaries.py tests/test_authorization.py tests/test_audit.py)
(cd backend && export WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set WORKSTREAM_TEST_DATABASE_URL}" && .venv/bin/python -m pytest -q tests/authorization/test_adapter_binding_registration.py tests/authorization/test_adapter_binding_authorization.py tests/compensation/test_adapter_binding_authorization_integration.py tests/compensation/test_adapter_binding_authorization_failures.py tests/compensation/test_adapter_binding_recovery.py tests/compensation/test_adapter_binding_owner_fences.py tests/compensation/test_adapter_binding_service.py tests/compensation/test_adapter_binding_database_guards.py tests/compensation/test_adapter_binding_persistence.py tests/architecture/test_authorization_boundary.py tests/architecture/test_module_boundaries.py tests/test_authorization.py tests/test_audit.py --cov=app.modules.authorization.adapter_binding_authorization --cov=app.modules.authorization.api.adapter_bindings --cov=app.modules.authorization.domain.adapter_bindings --cov=app.modules.authorization.domain.prepared_adapter_bindings --cov=app.adapters.auth.adapter_bindings --cov-fail-under=90)
(cd backend && .venv/bin/python -m scripts.test_structure_boundary validate --policy ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_POLICY.md --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json)
(cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
python3 scripts/check_markdown_links.py
git diff --check
gh pr checks <PR-number> --watch
```

Hosted GitHub Actions owns the full PostgreSQL matrix and repository-wide
coverage run. The local machine must not run the full suite.

The focused coverage command measures the materially changed AUTH
adapter/evaluator modules. Existing catalogue, kernel, PREP, package-export,
composition-root, and CON injection files receive exact behavioral assertions
in the listed tests plus GitHub's repository-wide coverage gate; adding those
large parity surfaces to one combined focused percentage would obscure rather
than prove the new boundary. The unchanged
`app.modules.compensation.api.adapter_bindings` public contract and its existing
API tests are explicitly outside this changed-module percentage; CP03B only
injects its already-defined port. Sub-agent session closure is verified by the
executing agent at completion, not by an invented repository command.

## Required reviewers

- architecture
- security/auth
- product/operations
- QA
- test delta
- CI integrity
- senior engineering
- reuse/dedup
- documentation

All Critical and High findings are fixed before readiness. Every external
finding is replayed against the exact head and fixed only when valid.

## Human review focus

Confirm that only covered human Finance Authority can cross the four exact
CP02 boundaries; resource and transaction binding are complete; duplicate
recovery does not mint mutation authority; CON ownership/fences remain intact;
and no adjacent compensation action, service identity, route, or migration is
activated.

## Stop conditions

Stop and amend/re-review this contract if implementation needs:

- another action, permission, principal, role, service identity, or resource
  fact;
- a migration, route, CON lifecycle change, or new product behavior;
- a generic compensation evaluator or another PREP protocol;
- a private cross-module import or second composition path;
- weakened authorization, boundary, test, or CI proof.
