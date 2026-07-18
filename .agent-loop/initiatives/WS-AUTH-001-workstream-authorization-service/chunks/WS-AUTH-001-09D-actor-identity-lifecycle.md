# Chunk Contract: WS-AUTH-001-09D - Actor And Identity-Link Lifecycle Mutations

## Goal

Activate actor suspension/reactivation/deactivation and identity-link
revoke/reactivate with terminal history, idempotent atomic evidence, immediate
invalidation, and final Access Administrator concurrency safety.

## Allowed files

```text
backend/app/modules/actors/**
backend/app/modules/authorization/**
backend/app/modules/audit/**
backend/app/api/router.py
backend/app/api/deps/authorization.py
backend/tests/test_actors.py
backend/tests/test_auth.py
backend/tests/test_authorization.py
backend/tests/test_audit.py
backend/tests/test_api_controls.py
backend/tests/test_api_rate_controls.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-09D.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
new table or migration
deactivation reversal or actor/link deletion
new or replacement identity-link creation
service, AdminRoleGrant, ProjectRoleGrant, or Contributor authority changes
task, review, assignment, or revision lifecycle mutation
artifact action activation or adapter attachment
```

## Exact surfaces

```text
POST /api/v1/actors/{actor_profile_id}/suspend
POST /api/v1/actors/{actor_profile_id}/reactivate
POST /api/v1/actors/{actor_profile_id}/deactivate
POST /api/v1/actor-identity-links/{identity_link_id}/revoke
POST /api/v1/actor-identity-links/{identity_link_id}/reactivate
```

Each route declares the identically named registered ActionId and PermissionId.
Only an effective Access Administrator candidate is valid. Bodies contain one
required normalized reason; mutations use an `Idempotency-Key` and the admin
mutation limiter.

## State and replay contract

| Operation | Allowed current state | New-key conflict |
|---|---|---|
| suspend profile | active | `actor_already_suspended` or `actor_deactivated_terminal` |
| reactivate profile | suspended | `actor_not_suspended` or `actor_deactivated_terminal` |
| deactivate profile | active or suspended | `actor_deactivated_terminal` |
| revoke link | active link | `identity_link_already_revoked` |
| reactivate link | revoked link and non-deactivated profile | `identity_link_not_revoked` or `actor_deactivated_terminal` |

An exact committed replay is resolved only after current caller authority is
revalidated and returns the original result/evidence reference. A mismatched
payload returns `idempotency_mismatch`. Reactivation never restores a separately
revoked grant. Suspended-to-deactivated preserves suspension attribution and
adds terminal deactivation attribution; deactivation is irreversible.

## Atomic lock and evidence contract

Final-admin-affecting mutations use one order in the route-owned transaction:
`AuthorityControl(id=1) FOR UPDATE`; all acting and target principals ordered by
ActorProfile ID; for each human, ActorProfile then exact ActorIdentityLink and
exact matched grant; exact idempotency reservation; effective-admin count after
the proposed transition; state, success event, exactly one invalidation
obligation, and idempotency completion; commit.
The effective count requires an active human profile, active identity link, and
active system-scoped Access Administrator grant. Self-suspend,
self-deactivate, final-admin loss, and unsafe concurrent different-target
combinations fail without partial state.

## Boundary and acceptance

- Exactly five actions activate: final totals are 65 actions, 17 active and 48
  planned. Every route has one generated manifest declaration.
- State, idempotency, success evidence, and invalidation commit atomically;
  evidence/SQL/commit failure returns stable retryable 503 and rolls back all
  partial state. Denial/conflict evidence follows the closed audit contract.
- Same-target races and mixed link-revoke/grant-revoke/suspend/deactivate races
  leave at least one effective, authenticatable Access Administrator.
- Only successful caller verification timestamps advance. Target verification
  timestamps never advance from administration, reactivation is not token
  verification, and replay/denial/failure behavior is explicit in tests.
- AUTH-09D emits the durable invalidation obligation but does not mutate task or
  review state. AUTH-13 and WS-REV own consumption; no `needs_revision` work is
  returned to ready here.
- Focused actor and authorization coverage is at least 90 percent; GitHub
  Backend preserves the repository-wide 78 percent floor.

## Risk and reviewers

L1 / P1. Required: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts/api_contract_e2e.py)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q \
  tests/test_actors.py tests/test_auth.py tests/test_authorization.py \
  tests/test_audit.py tests/test_api_controls.py tests/test_api_rate_controls.py \
  tests/test_alembic.py)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Human review focus

Review terminal state transitions, exact replay ordering, route-owned atomicity,
shared final-admin locking, caller-only verification timestamps, and downstream
invalidation without consumer-state mutation.

## Stop condition

Stop if any consumer lifecycle must be mutated or service authority must be
treated as a human grant. Stop after merge and signed memory; AUTH-09E requires
a new explicit start.
