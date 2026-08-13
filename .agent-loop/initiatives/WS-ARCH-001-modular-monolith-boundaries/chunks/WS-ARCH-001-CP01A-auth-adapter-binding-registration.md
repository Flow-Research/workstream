# Chunk Contract: WS-ARCH-001-CP01A — AUTH Adapter-Binding Registration

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Register the exact adapter-binding authorization contract while every new
action remains planned and unavailable.

## Why this chunk exists

CON CP02 cannot implement hidden binding behavior against invented identifiers
or an untyped AUTH seam. This chunk reserves only the four operations CP02
needs. Dependency-aware retirement remains later; fulfillment, callbacks, and
delivery are separate security boundaries.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/api/__init__.py
backend/app/modules/authorization/api/action_ids.py
backend/app/modules/authorization/api/adapter_bindings.py
.ci/behavior-ownership/partition.v1.json (additive AUTH target parity only)
backend/scripts/behavior_ownership.py (exact CP01A public-API target only)
backend/tests/test_behavior_ownership.py (exact additive-transition parity only)
backend/tests/authorization/test_adapter_binding_registration.py
backend/tests/test_authorization.py (closed catalogue/action-owner parity only)
docs/operations_authorization_service.md (catalogue parity only)
docs/spec_authorization_service.md (catalogue parity only)
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md (catalogue parity only)
docs/spec_contribution_compensation.md (CP01A registration parity only)
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/STATUS.md (CP01A state only)
docs/roadmap_status.md (CP01A capability state only)
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json (generated parity only)
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/{CHUNK_MAP.md,STATUS.md}
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP01A-auth-adapter-binding-registration.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP01A-*.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/{CHUNK_MAP.md,STATUS.md}
```

## Not allowed

```text
CON application/model/repository/route changes
database migrations or persisted service rows
evaluators, grants, service identities, fixed-service matrix rows, or activation
compensation.adapter_binding.retire
fulfillment, callback, dispatcher, award, TASK, REV, or delivery authority
generic resource dictionaries or a second prepared-authorization protocol
compatibility aliases or non-canonical policy naming
```

## Exact registration manifest

| ActionId | PermissionId | Context |
|---|---|---|
| `compensation.adapter_binding.read` | `compensation.adapter_binding.manage` | exact project and binding identity |
| `compensation.adapter_binding.create` | `compensation.adapter_binding.manage` | exact project, instrument, unit, adapter actor, and non-secret route facts |
| `compensation.adapter_binding.suspend` | `compensation.adapter_binding.manage` | exact project and active binding identity |
| `compensation.adapter_binding.resume` | `compensation.adapter_binding.manage` | exact project and suspended binding identity |

## Acceptance criteria

- [ ] Four closed ActionIds map only to existing
  `compensation.adapter_binding.manage` under CP01A custody.
- [ ] All four definitions remain `PLANNED`; no evaluator, identity, grant,
  matrix row, route, or product behavior can use them.
- [ ] AUTH public API exposes typed immutable query/mutation fact models and
  canonical resource-digest helpers without importing CON internals.
- [ ] Mutation facts can be carried by the existing opaque PREP port; no handle
  construction, serialization, consumption, or runtime evaluator is added.
- [ ] Independent tests prove identifier spelling, permission/owner mapping,
  typed fact validation and digest domain separation, catalogue/API parity,
  and planned denial.
- [ ] Retirement/callback/fulfillment identifiers are absent.

## Verification commands

```bash
cd backend && uv run ruff check app/modules/authorization tests/authorization/test_adapter_binding_registration.py
cd backend && uv run pytest -q tests/authorization/test_adapter_binding_registration.py tests/test_authorization.py
python3 scripts/workstream_agent_gate.py --help
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
python3 scripts/check_markdown_links.py
git diff --check
```

Hosted CI owns the full repository coverage gate. Authorization remains at or
above 90 percent and repository-wide coverage remains at or above 78 percent.

## Required reviewers

- [ ] architecture
- [ ] security/auth
- [ ] senior engineering
- [ ] QA/test
- [ ] product/ops
- [ ] reuse/dedup
- [ ] test delta
- [ ] docs

## Human review focus

Confirm the exact four-action manifest, the exclusion of retirement and all
service/callback authority, and proof that registration cannot activate use.

## Stop conditions

Stop if CP02 needs another action, permission, resource fact, evaluator,
identity, migration, or product import; update and re-review the contract first.

## Merge state

- Outcome on merge: `complete`
