# Chunk Contract: WS-AUTH-001-12F2 — Manual Submission Policy Drafts

## Status and prerequisite

Proposed and inactive after merged 12F1. Risk: L1.

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
backend/app/modules/projects/submission_policy_mutation_service.py
backend/app/modules/projects/submission_policy_mutation_repository.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/operations_project_operating_manual.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed

Agent derivation, approval, effective/pre-submit compilation, Celery execution,
post-submit behavior, compatibility routes, or edits to agent-derived drafts.

## Acceptance

- Activate only `project.submission_artifact_policy.create` and
  `project.submission_artifact_policy.update` for a human Project Manager with
  an exact active project grant. Admin role name alone, token claims, service
  membership, or a contributor grant cannot substitute.
- Both routes require a valid UUID `Idempotency-Key` before actor provisioning,
  use the dedicated PREP dependency, expose exact OpenAPI action metadata, and
  reject service tokens at the public boundary.
- Create locks exact project/draft guide/latest snapshot/sufficiency/setup
  generation and binds the canonical manual payload digest. Update additionally
  locks the exact draft policy ID/status/hash and compare-and-swaps that hash.
- The exact authoritative sufficiency report must match the snapshot and setup
  generation and be `passed`, or `passed_with_warnings` with the same report's
  warnings acknowledged. Missing, blocked, stale, diagnostic-only, or
  unacknowledged-warning reports deny without policy/replay/evidence mutation.
- Manual payload validation preserves every non-bypassable Workstream default
  submission rule. It may tighten project requirements but cannot disable,
  replace, or weaken the startup-fixed default policy/catalogue floor.
- Manual rows record complete local actor/link/grant/project/action/decision
  provenance and `manual` derivation source. Agent provenance fields must be
  null. Agent-derived rows are immutable through this path.
- Exact committed replay reauthorizes then returns the stored response without
  another mutation. Changed/pending/cross-action/link-substitution reuse denies.
  Concurrent exact calls produce one row/update; fault injection rolls back
  policy, replay completion and allowed evidence together.
- Existing legacy role-based create/update calls are removed, not retained as
  fallback aliases.

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
