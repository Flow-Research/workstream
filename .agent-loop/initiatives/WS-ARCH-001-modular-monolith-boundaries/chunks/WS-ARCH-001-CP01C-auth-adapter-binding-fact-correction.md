# Chunk Contract: WS-ARCH-001-CP01C — AUTH Adapter-Binding Fact Correction

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Correct the unavailable adapter-binding authorization facts before CP02 builds
CON behavior against them.

## Why this chunk exists

Pre-CP02 review found that CP01A bound creation to a compensation unit even
though a binding is scoped only by project and instrument, omitted the
server-selected binding identity, and omitted the exact lifecycle version from
suspend/resume mutations. Leaving those facts unchanged would create
AUTH/product digest drift and permit authorization of an imprecise row
generation. All four actions are still planned and unavailable, so this is a
clean contract correction with no compatibility path.

## Risk class

L1

## Allowed files

```text
backend/app/modules/authorization/api/adapter_bindings.py
backend/tests/authorization/test_adapter_binding_registration.py
.ci/behavior-ownership/auth/adapter-binding-facts.json
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json (generated parity only)
docs/spec_authorization_service.md (fact-contract parity only)
docs/operations_authorization_service.md (fact-contract parity only)
docs/spec_contribution_compensation.md (fact-contract parity only)
docs/roadmap_status.md (sequence parity only)
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/{PLAN.md,CHUNK_MAP.md,STATUS.md}
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP01C-auth-adapter-binding-fact-correction.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP01C-*.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/{CHUNK_MAP.md,STATUS.md,ACTIVATION_CUSTODY.md}
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/{CHUNK_MAP.md,STATUS.md,AUTHORIZATION_HANDOFF.md}
```

## Not allowed

```text
CON models, repositories, services, routes, or tests
database schema, baseline, migration, trigger, or reference-data changes
catalogue identifiers, permissions, action owners, or availability changes
evaluators, grants, identities, fixed-service rows, or activation
adapter-binding retirement, policy behavior, fulfillment, callbacks, or delivery
compatibility aliases, dual digest formats, or acceptance of the retired facts
```

## Exact corrected facts

- Create binds `project_id`, server-selected `adapter_binding_id`,
  `instrument_type`, `adapter_actor_id`, and canonical non-secret `route_key`.
- `instrument_type` is the exact unchanged closed value read from CON's
  server-owned adapter binding. CON copies it into the AUTH facts; AUTH does
  not translate it, import CON models, or redefine CON instrument rules.
- Create does not bind a compensation unit; units are independent
  `ProjectCompensationUnit` identities.
- Suspend binds `project_id`, `adapter_binding_id`, `expected_status=active`,
  and positive `expected_lifecycle_version`.
- Resume binds `project_id`, `adapter_binding_id`,
  `expected_status=suspended`, and positive
  `expected_lifecycle_version`.
- Read remains bound to exact project and binding identity.

## Acceptance criteria

- [x] `AdapterBindingCreateFacts` requires a UUID binding identity and no
  longer exposes `unit`; it names the unchanged CON-owned value exactly
  `instrument_type` and exposes no compatibility alias named `instrument`.
- [x] Suspend/resume facts require a strictly positive integer lifecycle
  version; booleans, zero, negatives, and non-integers fail closed.
- [x] Canonical digests change with binding identity or lifecycle version and
  retain action/type/domain separation.
- [x] Retired fact shapes have no compatibility constructor, alias, or digest
  path.
- [x] The existing four actions remain mapped exactly as CP01A registered them
  and remain planned/unavailable.
- [x] Behavior-ownership and structural-debt records are reconciled without
  admitting new debt.
- [x] Current plans and status documents project CP01C complete on merge and
  CP02 as the next boundary.
- [x] Active ARCH, AUTH, CON, roadmap, and current-state ledgers project CP01C
  between CP01B and CP02. CP02's non-executable skeleton remains untouched and
  must be replaced by its own current-main executable contract before coding.

## Verification commands

```bash
cd backend && uv run ruff check app/modules/authorization/api/adapter_bindings.py tests/authorization/test_adapter_binding_registration.py
cd backend && WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set a disposable migrated test database URL}" uv run pytest -q tests/authorization/test_adapter_binding_registration.py tests/test_authorization.py
cd backend && uv run python -m scripts.behavior_ownership validate --group auth --trusted-revision origin/main --head-revision HEAD
cd backend && uv run python -m scripts.test_structure_boundary validate --policy ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_POLICY.md --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
python3 scripts/check_markdown_links.py
git diff --check
```

Hosted CI owns the complete repository coverage gate. Authorization coverage
must remain at or above 90 percent and repository-wide coverage at or above 78
percent.

## Required reviewers

- [x] architecture
- [x] security/auth
- [x] senior engineering
- [x] QA/test
- [x] product/ops
- [x] reuse/dedup
- [x] test delta
- [x] docs

## Human review focus

Confirm that the corrected facts match the persisted binding identity and
lifecycle generation exactly, that no compatibility surface remains, and that
all actions remain unavailable.

## Stop conditions

Stop if CP02 needs another action, permission, principal, resource fact,
database change, or AUTH runtime component; update and re-review the contract
before implementation.

## Merge state

- Outcome on merge: `complete`
