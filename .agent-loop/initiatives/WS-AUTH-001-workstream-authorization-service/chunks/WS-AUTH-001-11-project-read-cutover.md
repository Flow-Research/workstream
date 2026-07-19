# Chunk Contract: WS-AUTH-001-11 - Project Identity, Guide, Source, And Visibility Cutover

## Status

Proposed and inactive. The exact project read/list ActionId inventory and
then-current migration mapping delta must be added before implementation review.

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Move project identity reads, guide/source reads, setup-status visibility, and
policy-summary queries from token roles to scoped local permissions without
changing project setup mutations.

## Why this chunk exists

Separating query/visibility cutover from policy mutations keeps project
authorization reviewable and proves anti-IDOR filtering before write cutover.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/projects/router.py
backend/app/modules/projects/service.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/schemas.py
backend/app/modules/authorization/**
backend/app/modules/audit/**
backend/alembic/versions/<then-current-next>_*.py
backend/app/api/deps/auth.py
backend/tests/test_projects.py
backend/tests/test_auth.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-11.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
project create/update, guide/source mutation, policy approval, activation
task/submission/checker authorization
issuer-role fallback or authorization pagination after unfiltered counts
```

## Acceptance criteria

- Project Managers read only covered projects; system scope covers all projects
  only for registered Project Manager permissions.
- Operator, Finance Authority, and Audit Authority receive only their defined
  minimal project views.
- Access Administrator and contributor grants do not imply project-management
  visibility.
- An active submitter, reviewer, or adjudicator grant independently allows the
  minimal `project.read` projection for its exact project, without management
  fields or permissions. Each role has exact-project allow, cross-project deny,
  minimal-field, concealed-not-found, and pre-filtered count/cursor tests.
- The adjudicator grant supplies no adjudication action in this chunk; it adds
  only the same minimal exact-project read projection.
- One actor may hold all three rows. A decision records the exact matched grant,
  never a synthetic combined role. Revoking one role preserves minimal
  `project.read` when another eligible exact-project role remains, and changes
  no AdminRoleGrant.
- Canonical project scope is resolved before filtering, counts, and cursors.
- Every migrated project read/list route declares one primary registered action
  and its canonical project or collection-parent target; permission strings and
  secondary role policy do not live in the router.
- Generated OpenAPI/command manifest-delta tests prove every protected project
  read/list surface migrated here has exactly one active `ActionId` declaration.
- Before runtime edits, the contract enumerates every new ActionId, existing
  PermissionId mapping, canonical target, principal class, facts, guards, and
  surface. The then-current migration updates typed/PostgreSQL action-evidence parity and
  proves prior-head upgrade, downgrade, re-upgrade, and fresh replay.
- ProjectRepository remains the canonical project/guide/source persistence
  query owner and returns domain records. The project application service or a
  feature-owned resource loader composes ResourceContext; persistence does not
  depend on authorization DTOs, and authorization does not re-query project
  tables through a parallel repository.
- Hidden project/resource existence is not leaked through errors or totals.
- No migrated query uses `require_any_role()` or token roles.
- Full backend suite and API contract drill pass.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q \
  tests/test_authorization.py tests/test_auth.py tests/test_projects.py \
  --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic upgrade head)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic downgrade -1)
(cd backend && WORKSTREAM_DATABASE_URL=<isolated-test-db> .venv/bin/alembic upgrade head)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Review query scope, minimal disclosure, pagination/count concealment, and that
mutation behavior is untouched.

## Stop conditions

Stop if safe query cutover requires changing setup mutations or accepting a
token-role fallback.
