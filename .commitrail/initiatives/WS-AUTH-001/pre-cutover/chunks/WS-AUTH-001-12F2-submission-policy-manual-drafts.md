# Chunk Contract: WS-AUTH-001-12F2 — Manual Submission Policy Drafts

## Status and prerequisite

Authorized for implementation after merged 12F1. Risk: L1. The original
contract failed pre-implementation architecture, security, and QA review; the
review corrections below are part of the implementation boundary.

## Goal

Activate Project Manager-only manual draft create/update as an explicitly
manual, idempotent exception path with no agent provenance.

## Allowed files

```text
backend/app/api/deps/authorization.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/modules/projects/router.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/service.py
backend/app/modules/projects/submission_policy_mutation_service.py
backend/app/modules/projects/submission_policy_mutation_repository.py
backend/tests/test_authorization.py
backend/tests/test_alembic.py
backend/tests/test_projects.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/operations_project_operating_manual.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed

Agent derivation, approval, effective/pre-submit compilation, Celery execution,
post-submit behavior, compatibility routes, in-place policy-body mutation, or
edits to agent-derived drafts. Changes to `projects/service.py` are limited to
extracting one public, shared default-floor validator and removing the obsolete
self-committing create/update entry points; this chunk must not create a second
policy validator.

## Acceptance

- Activate only `project.submission_artifact_policy.create` and
  `project.submission_artifact_policy.update` for a human with an active,
  covered Project Manager `AdminRoleGrant`: either system scope or the exact
  project scope. A wrong-project grant, admin role name alone, token claims,
  service membership, or contributor grant cannot substitute. Attribute both
  actions to child owner `WS-AUTH-001-12F2`; the zero-activation 12F parent and
  derive/approve actions remain unavailable.
- Both routes require a valid UUID `Idempotency-Key` before actor provisioning,
  use the dedicated PREP dependency, expose exact OpenAPI action metadata, and
  reject service tokens at the public boundary.
- Create locks exact project/draft guide/latest snapshot/sufficiency/setup
  generation and binds the canonical manual payload digest. All acquisition
  paths use one order: project -> draft guide -> latest source snapshot -> setup
  run -> sufficiency report -> target draft policy (update only).
- Update requires `expected_policy_hash` and `successor_policy_version` in the
  request body. Both fields are part of the idempotency request digest and PREP
  resource facts. The successor policy ID is server-derived deterministically
  from the action, actor, identity link, project, selected predecessor, and
  idempotency key so exact retries bind the same identity without cross-actor
  collisions. PREP/replay bind predecessor policy ID,
  version, status and expected hash separately from successor policy ID and
  version; the runtime resource contract must expose both without overloading
  one `policy_id`/`policy_version` pair. Missing, malformed, cross-policy,
  duplicate-version, or stale values deny before mutation. Update is
  append-only: it creates a new manual draft row with
  `creation_action_id=project.submission_artifact_policy.update`, complete fresh
  creation authority provenance, and `supersedes_policy_id` pointing to the
  selected draft; it atomically marks the old draft superseded. It never
  rewrites an existing policy body/hash in place.
- The exact authoritative sufficiency report must match the snapshot and setup
  generation and be `passed`, or `passed_with_warnings` with the same report's
  warnings acknowledged through the exact 12E-authorized acknowledgement.
  Warning acceptance requires non-null actor profile, identity link, matched
  Project Manager grant, action, decision event, scope project, timestamp, and
  the same report/snapshot/setup-generation lineage. Legacy role-string-only
  acknowledgement is insufficient. Missing, blocked, stale, diagnostic-only,
  or incompletely acknowledged reports deny without policy/replay/evidence
  mutation.
- Manual payload validation preserves every non-bypassable Workstream default
  submission rule. It may tighten project requirements but cannot disable,
  replace, or weaken the startup-fixed default policy/catalogue floor.
- Manual rows record complete local actor/link/grant/project/action/decision
  provenance and the canonical persisted manual derivation token
  `manual_admin_derivation`. This token describes provenance; it does not grant
  authority. Agent provenance fields must be null. Agent-derived rows are
  immutable through this path.
- Exact committed replay reauthorizes then returns the stored response without
  another mutation. Create and update return their normal committed success
  status on replay and return the originally stored response JSON, never a
  later current-row projection. Changed/pending/cross-action/link-substitution
  reuse denies. Concurrent exact calls produce one append-only result.
- Replay reservation, replacement policy staging, predecessor supersession,
  local authority provenance, AUTH evidence, and replay completion share one
  root transaction. Fault injection after replay reservation, policy staging,
  AUTH evidence staging, and replay completion-before-commit must roll all of
  them back together.
- Manual mutation may read and lock setup-run/generation state but cannot set
  setup outputs, advance setup status/current step, enqueue continuation, or
  impersonate the 12F3 derived-policy output.
- Public routes use only the new mutation service and route-owned
  commit/rollback. Existing self-committing, role-based `ProjectService`
  create/update calls are removed, not retained as fallback aliases.

## Verification commands

```bash
cd backend
.venv/bin/ruff check app tests scripts
.venv/bin/pytest -q tests/test_authorization.py -k 'submission_artifact_policy and (create or update)'
.venv/bin/pytest -q tests/test_projects.py -k 'submission_artifact_policy and (create or update or manual or idempotency)'
.venv/bin/pytest -q tests/test_ci_test_lanes.py
.venv/bin/coverage erase
.venv/bin/coverage run --source=app.modules.projects,app.modules.authorization --concurrency=greenlet -m pytest -q tests/test_authorization.py -k 'submission_artifact_policy and (create or update)'
.venv/bin/coverage run --source=app.modules.projects,app.modules.authorization --concurrency=greenlet --append -m pytest -q tests/test_projects.py -k 'submission_artifact_policy and (create or update or manual or idempotency)'
.venv/bin/coverage report --include='app/modules/projects/submission_policy_mutation_*.py,app/modules/authorization/catalogue.py,app/modules/authorization/kernel.py,app/modules/authorization/prepared.py,app/modules/authorization/runtime.py' --precision=2 --fail-under=90
.venv/bin/python scripts/api_contract_e2e.py
cd ..
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

Every selector must be non-zero; exact pushed head passes Agent Gates and full
hosted Backend. Required reviewers: all L1 tracks. Human focus: manual-only
provenance, agent immutability, PM grant isolation and replay atomicity.

The focused selectors must contain child-owned 12F2 tests, not merely collect
older parent or legacy tests. API E2E must assert exact OpenAPI action metadata,
successful create/update and exact replay, plus denial for service tokens,
contributors, wrong-project grants, role claims, and missing/invalid
idempotency or update-precondition input. Focused tests must also prove system
and exact-project Project Manager grants succeed; wrong-project grants fail;
default-floor weakening, agent-row update, stale acknowledgement/lineage, stale
or concurrent CAS, copied/cross-action replay, and each named fault-injection
point leave no protected mutation or allowed evidence.
