# Chunk Contract: WS-ARCH-001-CP01B — AUTH ContributionPolicy Registration

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Register the canonical ContributionPolicy authorization contract while every
new action remains planned and unavailable.

## Why this chunk exists

CP04 needs stable `contribution.policy.*` identifiers and typed AUTH facts, but
policy registration must not inherit adapter-binding behavior or activate a
Finance operation before hidden CON proof exists.

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
backend/app/modules/authorization/api/contribution_policies.py
backend/tests/authorization/test_contribution_policy_registration.py
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/{CHUNK_MAP.md,STATUS.md}
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-CP01B-auth-contribution-policy-registration.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-CP01B-*.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/{CHUNK_MAP.md,STATUS.md}
```

## Not allowed

```text
CON application/model/repository/route changes
database migrations or persisted service rows
evaluators, grants, service identities, fixed-service matrix rows, or activation
adapter-binding lifecycle behavior
fulfillment, callback, dispatcher, award, TASK, REV, or delivery authority
generic resource dictionaries or a second prepared-authorization protocol
compatibility aliases or non-canonical ContributionPolicy identifiers
```

## Exact registration manifest

| ActionId | PermissionId | Context |
|---|---|---|
| `contribution.policy.read` | `compensation.policy.manage` | exact project, policy, and optional version identity |
| `contribution.policy.create_draft` | `compensation.policy.manage` | exact project and policy collection |
| `contribution.policy.update_draft` | `compensation.policy.manage` | exact project, policy, and draft version identity |
| `contribution.policy.publish` | `compensation.policy.manage` | exact project, policy, complete draft version, rule/definition digest, and referenced binding identities |
| `contribution.policy.retire` | `compensation.policy.manage` | exact project, policy, and published version identity |

## Acceptance criteria

- [ ] Five canonical `contribution.policy.*` ActionIds map only to existing
  `compensation.policy.manage` under CP01B custody.
- [ ] All five definitions remain `PLANNED`; no evaluator, identity, grant,
  matrix row, route, or product behavior can use them.
- [ ] AUTH public API exposes typed immutable query/mutation fact models and
  canonical resource-digest helpers without importing CON internals.
- [ ] Mutation facts use the existing opaque PREP port; no handle construction,
  serialization, consumption, or runtime evaluator is added.
- [ ] Independent tests prove identifier spelling, permission/owner mapping,
  typed fact validation and digest domain separation, catalogue/API parity,
  and planned denial.
- [ ] No `compensation.policy.*` ActionId alias is introduced.

## Verification commands

```bash
cd backend && uv run ruff check app/modules/authorization tests/authorization/test_contribution_policy_registration.py
cd backend && uv run pytest -q tests/authorization/test_contribution_policy_registration.py tests/test_authorization.py
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

Confirm canonical ContributionPolicy terminology, exact five-action manifest,
binding lineage on publish, and proof that registration cannot activate use.

## Stop conditions

Stop if CP04 needs another action, permission, resource fact, evaluator,
identity, migration, or product import; update and re-review the contract first.

## Merge state

- Outcome on merge: `planned`
