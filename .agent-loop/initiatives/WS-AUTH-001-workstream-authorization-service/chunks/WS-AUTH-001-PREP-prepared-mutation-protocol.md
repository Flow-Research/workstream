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
backend/app/modules/authorization/**
backend/app/modules/actors/**
backend/app/modules/audit/**
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
dependency-teardown commit of an arbitrary shared session
serializable, reusable, cross-session, or caller-constructible prepared handles
```

## Acceptance criteria

- AUTH creates an internal, opaque, non-Pydantic, single-use
  `PreparedAuthorizationHandle` only after locking canonical current human or
  service authority. It is bound to the exact session, ActionId, actor reference
  kind, actor reference, idempotency key, and canonical request digest.
- The database lock order is exact: lock `AuthorityControl(id=1)` first when
  final-admin safety applies; order multiple authority principals by
  `ActorProfile.id`; for each human lock `ActorProfile`, its exact
  `ActorIdentityLink`, then its exact matched `AdminRoleGrant` or
  `ProjectRoleGrant`; for each service lock `ActorProfile` then its exact
  `ActorIdentityLink`. Only after every authority row is locked may the feature
  lock its rows in its documented order.
- `service_identity`, static service-action matrix membership, and action
  availability are immutable code-owned validations performed after the service
  profile/link locks. They are not database rows and must never be described or
  implemented as lock targets.
- The feature locks its records and recomposes final typed facts before AUTH
  evaluates exactly once and stages decision evidence.
- The route or service command owns one commit; AUTH and feature participants
  flush only.
- Reads retain request-scoped `require()`.
- Before feature mutation, handle consumption requires exact equality for
  session identity, ActionId, actor reference kind, actor reference, idempotency
  key, and canonical request digest. Stale, reused, wrong-action, cross-session,
  same-session/action cross-actor, same-session/action cross-request, serialized,
  caller-constructed, or authority-lost handles deny before feature mutation.
- Evidence SQL failure, participant failure, commit failure, timeout, and
  cancellation roll back all staged AUTH and feature state with a stable public
  error and no partial evidence.
- Lock-order, concurrency, rollback, denial-concealment, and at-least-90-percent
  focused authorization coverage are proven with real PostgreSQL behavior.
- Crossed concurrency proves PREP against identity-link revoke, actor suspend or
  deactivate, exact grant revoke, and final-admin mutations without deadlock,
  stale authorization, partial evidence, or partial feature state. Any existing
  inverse actor-self/admin/lifecycle lock path is reconciled before a PREP
  consumer is allowed to start.
- Replay/concurrency proof includes cross-actor and cross-request handle reuse in
  the same session and for the same action, and proves rejection does not consume
  a valid handle or stage feature/evidence state.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_auth.py tests/test_api_controls.py --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q)
python3 scripts/check_stale_authorization_docs.py
git diff --check
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
CI integrity, docs, reuse/dedup, and test delta.

## Human review focus

Review lock order, handle non-reusability, caller-owned commit, and complete
rollback under failure and cancellation.

## Stop conditions

Stop if AUTH must own a feature repository, if the caller cannot own one
transaction, or if evidence can commit separately from feature state.
