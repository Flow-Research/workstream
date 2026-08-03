# Chunk Contract: WS-XINT-003-02C — AUTH Catalogue And Principal Readiness

## Status

Current-main implementation contract refreshed from `ac52da6b`. Implementation
and internal review are complete; hosted exact-head evidence is pending.

## Parent initiative

`WS-XINT-003` — REV-AUTH End-to-End Contract.

## Goal

Install the complete approved v0.1 REV authorization catalogue, mappings,
fixed-service principals, and static service matrix once so REV implementation
cannot be interrupted by missing AUTH-owned values. Every review lifecycle
action remains unavailable.

## Why this chunk exists

The previous sequence deferred four ActionIds and six service identities until
late activation waves. REV therefore could not implement its lifecycle against
one stable AUTH surface. This chunk provides registration and admission without
granting execution authority.

## Risk class and SLA

L1 authorization catalogue, identity, and migration integrity. No expedited
review SLA.

## Allowed files

```text
backend/app/modules/actors/service_identities.py
backend/app/modules/authorization/catalogue.py
backend/alembic/versions/0049_rev_auth_readiness.py
backend/tests/test_authorization.py
backend/tests/test_alembic.py
backend/tests/test_auth.py
backend/tests/conftest.py (exact post-0049 public-schema fingerprint only)
docs/spec_authorization_service.md
docs/spec_review_lifecycle.md
docs/operations_authorization_service.md
docs/operations_roles_permissions.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/ACTION_CUSTODY.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/CHUNK_MAP.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/DECISIONS.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/DISCOVERY.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/REVIEW_LOG.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/STATUS.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/reviews/WS-XINT-003-02C-*.md
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/chunks/WS-XINT-003-02C-auth-catalogue-principal-readiness.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md
```

## Not allowed changes

- No REV queue, lease, finding, decision, revision, recovery, projection, or
  lifecycle implementation.
- No route, service job, provider I/O, action activation, or product release.
- No generic service principal or wildcard matrix membership.
- No compatibility aliases, duplicate permissions, dynamic service grants, or
  second authorization protocol.
- No XINT-002 action ownership or availability changes.

## Acceptance criteria

- All approved v0.1 `review.*` ActionIds in `ACTION_CUSTODY.md`, including the
  four formerly deferred recovery/lifecycle actions, exist exactly once in code
  and database parity and remain planned/unavailable.
- Existing PermissionIds are reused exactly as recorded; no PermissionId is
  added unless this plan is amended and reviewed again.
- The six exact REV fixed-service identities are closed registry values,
  provisionable through the canonical service-actor path, and mapped only to
  their recorded actions.
- The two identities sharing `review.reconcile.run` retain separate admitted
  identities and server-derived modes even though availability is global.
- Humans cannot use service actions; services cannot use human actions; every
  cross-service/action pair denies.
- Catalogue, migration, runtime owner, activation custody, static matrix, and
  service provisioning parity tests pass.
- Registration/provisioning produces no usable lifecycle authority while the
  action is unavailable.
- Migration upgrade/downgrade preserves exact parity and does not weaken any
  existing ART/AUTH or project authorization row.
- `review.finding_evidence.ingest` and
  `review.finding_response_evidence.ingest` receive an explicit
  `FUTURE_INTENT_REQUIRED_ACTIONS` catalogue invariant, remain planned, appear
  in no fixed-service matrix row, and cannot be selected by ordinary v0.1
  activation.
- The exact post-02C code catalogue is 71 PermissionIds, 100 ActionIds, 45
  active actions, and 55 planned actions. No existing active action changes.
- The new runtime activation custodians are exact: XINT-003-08A owns
  `review.revision_context.repair`, `review.revision_obligation.close`, and
  `review.revision_context.legacy_close`; XINT-003-08B owns
  `review.lifecycle.activation.manage`. Their new owner cardinalities are 3 and
  1. Existing 19 REV action owner rows/cardinalities remain unchanged until
  their individual activation waves.
- The exact fixed-service registry is 14 identities and the matrix is 14 rows
  with 22 memberships. The two reconciliation identities are separate rows
  sharing only `review.reconcile.run`.
- `0049_rev_auth_readiness` follows `0048_policy_authority`, adds only the four
  action/permission evidence pairs and six service-identity constraint values,
  and seeds no ActorProfile, ActorIdentityLink, grant, authority, route, or job.
- Downgrade locks evidence and actor tables first, refuses every direct or
  idempotency-linked use of the four actions, refuses use of every new service
  identity, and otherwise restores the exact 0048 constraints.
- Tests named `test_xint003_02c_rev_auth_readiness_schema_and_roundtrip`,
  `test_xint003_02c_rev_auth_readiness_guarded_action_evidence_downgrade`, and
  `test_xint003_02c_rev_auth_readiness_guarded_identity_downgrade` prove the
  empty round trip and every action/evidence-shape/identity refusal.
- `test_xint003_02c_provisions_all_six_review_service_identities` exercises the
  canonical service-actor API for every new identity without granting usable
  lifecycle authority.

## Verification commands

```bash
(cd backend && .venv/bin/ruff check \
  app/modules/actors/service_identities.py \
  app/modules/authorization/catalogue.py \
  alembic/versions/0049_rev_auth_readiness.py \
  tests/test_authorization.py tests/test_alembic.py tests/test_auth.py)
(cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest \
  -p pytest_asyncio.plugin -q \
  tests/test_authorization.py \
  -k 'closed_permission_and_action_catalogue or fixed_service or rev_custody')
(cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest \
  -p pytest_asyncio.plugin -q \
  tests/test_auth.py -k 'service_actor or xint003_02c')
(cd backend && .venv/bin/coverage erase && \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/coverage run -m pytest \
  -p pytest_asyncio.plugin -q \
  tests/test_authorization.py tests/test_auth.py \
  -k 'closed_permission_and_action_catalogue or fixed_service or rev_custody or service_actor or xint003_02c' && \
  .venv/bin/coverage report \
  --include='app/modules/actors/service_identities.py' \
  --precision=2 --fail-under=90 && \
  .venv/bin/coverage report \
  --include='app/modules/authorization/catalogue.py' \
  --precision=2 --fail-under=90)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python scripts/run_test_lanes.py \
  --lane schema_contracts_a --metadata-dir .ci/xint-003-02c/schema-a \
  --summary-json .ci/xint-003-02c/schema-a.json --timeout-seconds 1200)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python scripts/run_test_lanes.py \
  --lane schema_contracts_b --metadata-dir .ci/xint-003-02c/schema-b \
  --summary-json .ci/xint-003-02c/schema-b.json --timeout-seconds 1200)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_review_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check
```

GitHub's Backend workflow runs the complete sharded suite and combined coverage
report, preserving the repository-wide 78 percent floor. Changed authorization
and actor modules must remain at or above 90 percent coverage.

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
test delta, reuse/dedup, and docs.

## Human review focus

Confirm that the list is complete once, every service is least-privileged, and
nothing became available merely because it was registered or provisioned.

## Stop conditions

Stop on any new action/permission/principal requirement, uncertain migration
custody, or evidence that provisioning makes an unavailable action executable.
Merge this chunk and stop before 02D.
