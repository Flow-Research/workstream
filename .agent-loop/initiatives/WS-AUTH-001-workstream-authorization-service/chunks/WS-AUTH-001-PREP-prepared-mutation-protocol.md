# Chunk Contract: WS-AUTH-001-PREP - Prepared Mutation Authorization Protocol

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Add the AUTH-first, caller-committed prepared authorization protocol required
for sensitive cross-module mutations without changing feature behavior.

## Why this chunk exists

Request-scoped authorization against unlocked feature facts cannot guarantee
that authority, decision evidence, and business state remain consistent under
concurrency. Sensitive mutations need one explicit AUTH-first lock protocol and
one caller-owned transaction before feature cutovers consume it.

## Risk class

L1.

## SLA

P1. Sensitive cross-module mutation cutovers remain blocked until the prepared
protocol and its crossed-concurrency proof merge.

## Prerequisites

AUTH-09E is merged so human and fixed-service authority sources are structurally
separate and can be locked through one prepared protocol.

## Allowed files

```text
backend/app/api/deps/authorization.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/repository.py
backend/app/modules/authorization/runtime.py
backend/tests/test_authorization.py
backend/tests/test_auth.py
backend/tests/test_api_controls.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-PREP.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
feature repository imports or feature lifecycle mutations in AUTH
feature route, background-service, resource-composer, or adapter changes
new grant type, permission, action, service identity, or activation
ProjectRoleGrant model, table, repository, or pretend lock path before AUTH-10
catalogue, policy, migration, model, router, feature, or audit-schema changes
dependency-teardown commit of an arbitrary shared session
serializable, reusable, cross-session, or caller-constructible prepared handles
global capability registry, generic transaction manager, service locator, or caller callback
```

## Acceptance criteria

- This chunk implements the PREP foundation only for authority sources that
  exist on trusted `main`: grantless `actor_self`, one exact effective
  `AdminRoleGrant`, and fixed-service profile/link plus static code policy. It
  adds no `ProjectRoleGrant`; project-grant preparation fails closed as
  unsupported until AUTH-10 adds the row, repository lock, evaluator branch,
  and its own crossed-revoke proof before any project-authority consumer ships.
- The production surface is one `PreparedAuthorizationService` in
  `authorization/prepared.py` with strict typed inputs:
  `prepare(action_id, caller_input, requested_authority_scope) ->
  PreparedAuthorizationHandle` and `consume(handle, expected_action_id,
  caller_input, final_resource_context) -> AuthorizationDecision`. The caller's
  expected ActionId is required independently of the handle and must equal the
  privately stored prepared ActionId before the handle is consumed, facts are
  inspected, authority is evaluated, or evidence is staged. The requested scope is an
  untrusted actor-self/system/exact-project selector: AUTH normalizes and binds
  it privately, then derives exact scope from final facts and requires equality
  before evaluation. The caller may lock feature rows and recompose the final
  typed `AuthorizationResourceContext` only between these calls.
- `PreparedAuthorizationInput` is the only caller-constructible input: one
  bounded idempotency key and one strict JSON-compatible request value. A private
  `_PreparedAuthorizationBinding` is AUTH-derived and domain-separated over
  exact ActionId, context-derived actor reference kind/reference, normalized
  scope, key, and a canonical request-body digest computed with the existing
  hashing convention. `prepare` stores it; `consume` re-derives it. Callers
  cannot provide actor references, normalized scope, or a precomputed digest.
  PREP does not reserve or write `AuthorityIdempotencyRecord`; durable operation
  idempotency remains with the later owning command and existing
  `AuthorityMutationService`. Same-key/different-request and
  different-key/same-request bindings remain distinct and fail exact equality.
- AUTH creates an internal, opaque, non-Pydantic, non-dataclass, single-use
  `PreparedAuthorizationHandle` only after locking and validating canonical
  authority. It is bound to the issuing service instance, exact AsyncSession,
  exact active root transaction object, ActionId, context-derived actor
  reference, normalized authority scope, idempotency key, and canonical request
  digest.
- The handle has no public constructor or readable capability value. A
  service-local issuance registry requires exact object identity and an
  unpredictable private capability identity. Direct construction,
  `object.__new__`, attribute mutation, copy/deepcopy, pickle, JSON/Pydantic
  conversion, repr leakage, another service instance, another session, another
  root transaction, a nested/savepoint transaction, a closed transaction, or a
  new transaction on the same session fails before facts, evidence, or
  participant mutation.
- Handle state is exact: `issued -> consumed`. Binding mismatch or forgery does
  not consume the valid registered handle. The first exact binding attempt
  atomically marks it consumed before evaluation; denial, SQL/evidence failure,
  timeout, cancellation, participant failure, caller commit, or caller rollback
  can never make it reusable. Concurrent/reentrant consume permits exactly one
  evaluation/evidence path.
- Wrong-action proof uses two supported actions with compatible caller input and
  resource shapes where possible, plus supported-versus-unsupported and
  supported-versus-planned combinations. The caller-supplied expected ActionId
  is compared directly to the private binding; callers are never expected to
  infer intent from the returned decision.
- Current successful lock plans are closed and single-principal:

  | Supported active ActionId | Authority kind | Singleton | Resource context | Normalized scope |
  |---|---|---|---|---|
  | `actor.profile.update_self` | actor-self | no | `ActorSelfResourceContext` | exact caller profile |
  | `admin_role_grant.issue` | AdminRoleGrant | yes | `AdminRoleGrantIssueResourceContext` | system or exact context project |
  | `admin_role_grant.revoke` | AdminRoleGrant | yes | `AdminRoleGrantResourceContext` | system |
  | `actor.service.provision` | AdminRoleGrant | yes | `ServiceActorProvisionResourceContext` | system |
  | `actor.profile.suspend` | AdminRoleGrant | yes | `ActorProfileLifecycleResourceContext` | system |
  | `actor.profile.reactivate` | AdminRoleGrant | yes | `ActorProfileLifecycleResourceContext` | system |
  | `actor.profile.deactivate` | AdminRoleGrant | yes | `ActorProfileLifecycleResourceContext` | system |
  | `actor.identity_link.revoke` | AdminRoleGrant | yes | `ActorIdentityLinkLifecycleResourceContext` | system |
  | `actor.identity_link.reactivate` | AdminRoleGrant | yes | `ActorIdentityLinkLifecycleResourceContext` | system |

  Actor-self locks exact context `ActorProfile` then exact context
  `ActorIdentityLink`, with no grant. Every supported admin mutation preserves
  the current `_ADMIN_MUTATIONS` order: `AuthorityControl(id=1)`, exact request
  profile, exact context identity link, then the deterministic effective
  `AdminRoleGrant` selected by existing permission/scope precedence. The private
  issuance record stores the exact profile/link identities and lifecycle facts,
  normalized scope, matched grant identity/status, permission, and action.
  Unknown, planned, bootstrap, active read, action/resource mismatch,
  human/service-kind mismatch, and ProjectRoleGrant preparation fail unsupported
  before issuance. PREP supports no multi-principal plan; AUTH-10 must extend
  this table explicitly.
- Fixed services lock exact context profile then exact context link and run
  immutable service-identity, matrix, and availability validation. Every current
  matrix action is planned, so this chunk proves refreshed
  `action_unavailable` with no handle issuance and claims no positive service
  PREP capability. The first separately activated fixed-service consumer owns
  positive issue/consume and crossed-revocation proof.
- Reuse `AdminAuthorizationRepository.lock_control`, exact profile/link locking,
  deterministic `find_effective_grant(..., for_update=True)`,
  `authorization_resource_digest`, current `AuthorizationService` evaluation,
  `AuditService` staging, and the caller's AsyncSession. Add no parallel
  repository, digest, audit writer, UoW, transaction manager, or authorization
  evaluator. `PreparedAuthorizationHandle` is distinct from
  `AuthorityClaimHandle`; PREP binding composes with, but does not duplicate or
  reserve, the existing durable idempotency state machine.
- `kernel.py` adds one private AUTH-owned prelocked-authority seam. `consume`
  passes a private `_PrelockedAuthority` containing the exact locked context,
  normalized scope, and matched grant identity/facts. The seam verifies those
  same facts and final scope, reuses existing resource matching, lifecycle,
  policy/guard logic, `AuthorizationDecision`, resource digesting, and evidence
  staging, but performs no second request-authority control/profile/link/grant
  query, lock, or candidate selection. Existing target-resource guards may make
  their legitimate target actor/link/grant/project queries after the prepared
  binding and final scope are verified; these queries cannot replace or alter
  the locked request authority. Ordinary `require()` remains unchanged; no second
  evaluator or decision type is added. Exploding-query tests plus system/project,
  project-A/project-B, and same-role/two-grant cases reject substitution.
- `service_identity`, static service-action matrix membership, and action
  availability are immutable code-owned validations performed after the service
  profile/link locks. They are not database rows and must never be described or
  implemented as lock targets.
- This chunk ships no feature consumer, route, background command, or lifecycle
  cutover. A test-only PostgreSQL participant owned entirely by the test fixture
  proves protocol mechanics: the caller locks its neutral row after PREP,
  recomposes a final typed resource, calls `consume`, stages one participant
  mutation, and owns commit/rollback. Later feature chunks must prove their real
  row order, facts, guards, transaction owner, and crossed races independently.
- `prepare` stages no preliminary decision. After the test/future feature locks
  its records and recomposes final typed facts, `consume` invokes the prelocked
  kernel seam exactly once and stages exactly one bounded decision
  using the final resource digest. No arbitrary evaluator callback, feature
  repository import, service locator, or caller-provided lock function exists.
- A fixed-service planned-action preparation returns the refreshed bounded
  `action_unavailable` outcome without evidence because no final resource
  context exists and no handle is issued. A denial during exact `consume`
  stages one decision inside the caller transaction, then the caller-owned
  rollback removes that evidence with participant state; PREP never restages or
  commits denial evidence in a separate teardown transaction.
- The route or service command owns one commit; AUTH and feature participants
  flush only. `get_authorization_service` success teardown must not commit and
  PREP supplies no teardown commit path. The test command harness proves one
  explicit caller commit and rollback on every failure path.
- Reads retain request-scoped `require()`.
- Before participant mutation, consumption requires exact equality for issuer,
  session identity, root transaction identity/activity, caller-supplied expected
  ActionId, privately stored ActionId, context actor
  reference, idempotency key, and canonical request digest. Stale, reused,
  wrong-action, cross-service, cross-session, same-session/new-transaction,
  nested-transaction, same-action cross-actor, same-action cross-request,
  serialized, copied, caller-constructed, or authority-lost handles deny before
  participant mutation.
- Before evaluation, AUTH derives normalized scope from the supported final
  resource type and rejects any difference from the prepared scope. System to
  project, project to system, project A to project B, action/resource mismatch,
  or a different effective grant never reaches evidence, participant mutation,
  or a second authority lookup.
- Public outcomes are closed. Unknown/planned action, lifecycle loss, grant
  loss, scope/guard failure, and final-resource denial retain existing bounded
  authorization codes and concealment. Binding mismatch, forgery, and consumed
  capabilities return one generic prepared-handle-invalid error without
  decision evidence or hidden-resource lookup. SQL/evidence failure and bounded
  timeout use the existing sanitized retryable service-unavailable boundary.
  Participant and commit failures are caller-owned rollback failures. Original
  `asyncio.CancelledError`/`BaseException` propagates after rollback/cleanup; it
  is never converted into a stable public application error.
- Evidence contains only the existing bounded ActionId, PermissionId, final
  resource digest/reference, request/correlation IDs, actor reference, and
  matched authority. It never contains handle/capability identity, raw request,
  raw idempotency key, token, claims, or hidden feature facts.
- Evidence SQL failure, participant failure, commit failure, timeout, and
  cancellation roll back all staged AUTH and participant state with no partial
  evidence. The handle remains consumed after an exact attempt even when the
  database transaction rolls back.
- Lock-order, concurrency, rollback, denial-concealment, and at-least-90-percent
  focused authorization coverage are proven with real PostgreSQL behavior.
- Crossed concurrency covers identity-link revoke, actor suspend/deactivate,
  exact AdminRoleGrant revoke, and final-admin mutation in both orderings using
  independent sessions and explicit barriers/timeouts. Mutation-first makes
  PREP wait and deny from refreshed state with no allowed evidence/participant
  state; PREP-first makes the mutation wait through caller commit/rollback,
  evaluates once, then lets mutation proceed. Tests assert bounded completion,
  no deadlock, exact final rows, and zero partial evidence/participant state.
  The concurrent mutation caller uses the existing supported admin/lifecycle
  API/service transaction and targets the PREP request actor's exact profile,
  link, or grant. Both paths enter current kernel authorization through
  singleton -> request profile -> exact link -> matched grant before target
  locks. Tests preserve route/service behavior and explode on PREP consume-time
  authority re-lock. If an inverse whole-transaction path is observed, stop
  rather than hiding singleton locking in a generic repository getter.
- Replay/concurrency proof includes cross-actor and cross-request handle reuse in
  the same session and for the same action, and proves rejection does not consume
  a valid handle or stage feature/evidence state.
- Cancellation is injected while waiting for authority locks, after issuance,
  during test participant work, during evidence flush, and during caller commit.
  It propagates unchanged after rollback; the connection/session is reusable or
  explicitly invalidated, and authority, participant, idempotency, and evidence
  rows remain exact.
- Transaction identity is the stable underlying synchronous root
  `SessionTransaction` owned by the AsyncSession, never async-wrapper identity.
  `prepare` requires an already-active root and no nested/savepoint transaction;
  `consume` requires that exact root to remain current and active. Tests prove
  stable lookup, same-session/new-root, closed-root, and nested rejection.
- `get_prepared_authorization_service` in `api/deps/authorization.py` composes
  the request AsyncSession and resolved AuthorizationContext into one
  request-scoped `PreparedAuthorizationService`, which receives the existing
  `AuthorizationService`, repository, and audit staging through explicit
  constructors rather than private-field access. Existing
  `get_authorization_service` and all consumers remain unchanged; no route uses
  the new dependency here. The prepared dependency's `finally` calls `close()`
  without commit, invalidates outstanding handles, and releases issuance
  registry references. Consumed entries retain only a bounded tombstone needed
  for same-request replay rejection; transaction-change cleanup and teardown
  tests prove sessions/transactions cannot leak or preserve capabilities.
- No existing test is removed, skipped, xfailed, deselected, relaxed, or
  rewritten around broken behavior. Existing actor-self, admin, lifecycle,
  service, denial-evidence, concurrency, and dependency transaction tests remain
  green. No dependency override, fabricated product context, or direct grant
  insert is claimed as product-consumer proof.
- Trusted entry is `fe0e4492a7de8699c06a52921cbdaa8a1a22e567` and Alembic
  remains at `0029_shared_transactional_outbox`; `backend/alembic/**` has zero
  diff and no migration is added, edited, reserved, or allocated.
- Exactly one schema-v2 merge intent names same-initiative successor
  `WS-AUTH-001-10` with a separate explicit human start. This chunk performs no
  AUTH-10 work.
- Canonical specification and operations documentation state the exact current
  actor-self/AdminRoleGrant/fixed-service scope, transaction-bound handle state
  machine, no-feature-consumer boundary, cancellation propagation, caller-owned
  commit, and AUTH-10 ProjectRoleGrant extension obligation. Deterministic tests
  parse or assert those invariants in addition to stale-wording and link scans.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_auth.py tests/test_api_controls.py --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref fe0e4492a7de8699c06a52921cbdaa8a1a22e567
test -z "$(git diff --name-only fe0e4492a7de8699c06a52921cbdaa8a1a22e567 -- backend/alembic)"
(cd backend && test "$(.venv/bin/alembic heads | tr -d '[:space:]')" = "0029_shared_transactional_outbox(head)")
git diff --check
```

The local suite is focused because the user's machine is slow. After push, the
unchanged GitHub `Backend` workflow is authoritative for the isolated database
runner, complete backend suite, repository-wide coverage at or above 78
percent, authorization-subsystem coverage at or above 90 percent, and all
existing gates. This chunk changes no workflow, script, package command,
configuration, exclusion, or threshold.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
CI integrity, docs, reuse/dedup, and test delta.

## Human review focus

Review lock order, handle non-reusability, caller-owned commit, and complete
rollback under failure and cancellation.

## Stop conditions

Stop if AUTH must own a feature repository, if the caller cannot own one
transaction, or if evidence can commit separately from feature state.
