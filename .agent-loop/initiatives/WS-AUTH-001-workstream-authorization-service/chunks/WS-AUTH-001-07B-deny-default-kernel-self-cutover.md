# Chunk Contract: WS-AUTH-001-07B - Deny-By-Default Kernel And Self-Action Cutover

## Dependency

AUTH-07A must be merged with signed memory, followed by a separate explicit
human start.

## Goal

Implement the minimal request-scoped AuthorizationService and activate it only
for canonical actor self-read and self-update.

## Public feature interface

The application dependency constructs one request-scoped
`AuthorizationService` bound to the current `AuthorizationContext` and
caller-owned `AsyncSession`. Feature application services call only:

```python
decision = await authorization_service.require(
    action_id,
    typed_resource_context,
)
```

The service returns and stages one bounded `AuthorizationDecision`; it never
commits. It never accepts a raw `PermissionId`, candidate grant, guard, role, or
caller-authored resource fact. The caller owns commit/rollback and mutation
revalidation stays inside the same caller transaction. Feature modules own
their typed ResourceContext composers and lifecycle invariants and may import
only this public interface and closed AUTH types, never AUTH repositories,
models, grant loaders, or private evaluator helpers.

## Risk routing

- Risk class: L1
- SLA: P1
- Work type: authorization runtime, API cutover, audit evidence, tests, docs
- Human gate: explicit PR review and merge approval
- Required reviewers: senior engineering, QA/test, security/auth, product/ops,
  architecture, CI integrity, docs, reuse/dedup, test delta

## Allowed files

```text
backend/app/modules/authorization/**
backend/app/modules/audit/**
backend/app/modules/actors/repository.py
backend/app/modules/actors/service.py
backend/app/api/deps/authorization.py
backend/app/api/routes/auth.py
backend/app/api/router.py
backend/app/schemas/auth.py
backend/tests/test_authorization.py
backend/tests/test_audit.py
backend/tests/test_auth.py
backend/tests/test_actors.py
backend/tests/test_api_controls.py
backend/tests/test_app.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-07B.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
grant tables, grant queries, or role matrices
permission/admin-role definition APIs
project-scoped authorization-context API
feature resource loaders outside canonical actor self resources
cross-request decision caching
token-role authority or fabricated grants
generic policy language or a second unit-of-work abstraction
project/task/checker/review/contribution/artifact cutover
```

## Active action definitions

| ActionId | PermissionId | Target | Candidate source | Guards | Revalidate | Concealment | Owner |
|---|---|---|---|---|---|---|---|
| `actor.profile.read_self` | `actor.profile.read_self` | current canonical actor profile | active human self | active identity link; actor active or suspended; exact self target | no | none; caller owns target | AUTH-07B |
| `actor.profile.update_self` | `actor.profile.update_self` | current canonical actor profile | active human self | active identity link; actor active; exact self target; caller-owned fields only | yes, actor and link locked in caller transaction | none; caller owns target | AUTH-07B |

No other action becomes executable.

## Denial precedence

| Order | Condition | External status/code | Internal decision |
|---:|---|---|---|
| 1 | Missing or invalid bearer token | 401 existing auth code | no authorization decision |
| 2 | Unsupported subject kind or unprovisioned service | 403 existing actor code | no action evidence before canonical actor exists |
| 3 | Revoked identity link | 403 `identity_link_revoked` | denied with exact ActionId when transaction-local recheck observes revocation |
| 4 | Deactivated actor | 403 `actor_deactivated` | denied with exact ActionId when transaction-local recheck observes deactivation |
| 5 | Suspended actor on update | 403 `actor_suspended` | denied with exact ActionId |
| 6 | Unknown or planned action | 403 `permission_not_granted` at a public boundary | internal `unknown_action` or `action_unavailable` without leaking catalogue metadata |
| 7 | Target/fact mismatch | 403 `resource_guard_denied` | exact internal guard denial |
| 8 | No candidate permission | 403 `permission_not_granted` | exact internal candidate denial |

Suspended actors may read their own bounded profile but cannot update it. These
self routes do not conceal a separate resource, so they never collapse denial
to 404. Feature-owned concealment matrices begin in their owning cutover chunks.

## Transaction ownership

- The kernel validates and writes staged audit evidence but never commits.
- Read dependencies commit only the completed read decision evidence.
- Self-update revalidates and locks actor/link state, applies the bounded
  profile mutation, writes allow evidence, and commits once in the route-owned
  transaction.
- A denied self-update rolls back staged business changes before committing a
  clean denial event in a new transaction.
- Later mutation chunks must define their own lock order and race proof; this
  chunk proves the pattern only on self-update.

## Acceptance criteria

- `AuthorizationContext` contains canonical actor/link state and request/
  correlation IDs, never token roles or arbitrary client permissions.
- Closed strict `ActorSelfResourceContext` rejects missing, extra, mistyped, or
  non-self facts. A minimal `SystemResourceContext` extension type may exist but
  grants no system authority and has no active action.
- `AuthorizationDecision` is stable and privacy bounded, carrying ActionId,
  PermissionId, allowed/denial code, resource reference, matched authority kind,
  revalidation status, request ID, and correlation ID.
- Unknown permissions, unknown actions, and every planned action deny.
- The public feature interface has the exact two-argument request-scoped
  `require` contract above. An API-signature test rejects any session or `uow`
  argument, and import-boundary tests reject feature imports of AUTH persistence
  or private evaluation helpers and reject raw permission/candidate/guard input.
- System scope is not superuser authority.
- Default human authority is exactly the two self candidates above. Token role
  changes do not alter either decision.
- GET and PATCH `/api/v1/actors/me` each declare exactly one
  `x-workstream-action-id` in OpenAPI and call the central kernel.
- PATCH accepts only its existing caller-owned display fields and preserves its
  privacy contract.
- Real issuer-token tests resolve through the canonical actor dependency; no
  fabricated AuthorizationContext or direct grant rows count as API proof.
- Allowed and denied decision evidence carries the exact active ActionId.
- Deterministic tests prove revoked-link and suspension/deactivation rechecks,
  no cross-request cache, and a synchronized revoke-versus-update outcome
  without sleeps.
- OpenAPI inventory and API E2E proofs are updated without weakening their
  closed assertions.
- Permission/admin-role definition APIs remain deferred to AUTH-08.
- Project capability context remains deferred to AUTH-10 and no hidden project
  existence is exposed here.
- Materially changed authorization/dependency/route behavior remains at or
  above 90 percent branch coverage; global CI preserves the 78 percent floor.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts/api_contract_e2e.py)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<isolated-test-db> \
  .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_auth.py \
  tests/test_actors.py tests/test_api_controls.py tests/test_app.py \
  --cov=app.modules.authorization --cov=app.api.deps.authorization \
  --cov-branch --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<isolated-test-db> \
  .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

GitHub Backend remains authoritative for the full suite and repository-wide 78
percent floor.

## Human review focus

Review deny ordering, absence of token-role authority, exact self targeting,
suspended-read/update separation, transaction ownership, decision evidence,
OpenAPI declarations, and immediate state revalidation.

## Stop conditions

Stop if the kernel needs grant tables, project capability composition, feature
repositories, fabricated authority, or cross-request caching.

Stop after merge and signed memory. Do not start AUTH-08 automatically.
