# Chunk Contract: WS-AUTH-001-12F4 — Submission Policy Approval Chain

## Status and prerequisite

Proposed and inactive after merged 12F3. Risk: L1.

## Goal

Activate Project Manager approval and atomically persist the exact approved
draft, effective policy and compiled pre-submit policy with authorization evidence.

## Allowed files

```text
backend/app/api/deps/authorization.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/modules/checkers/catalogue.py
backend/app/modules/checkers/compiler.py
backend/app/modules/checkers/effective_plan.py
backend/app/modules/projects/models.py
backend/app/modules/projects/router.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/service.py
backend/app/modules/projects/setup_queue.py
backend/app/modules/projects/submission_policy_mutation_service.py
backend/app/modules/projects/submission_policy_mutation_repository.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/architecture_data_model.md
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/operations_project_operating_manual.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

12F1 owns every new approval/effective/pre-submit provenance column. 12F4
allocates no migration and may not edit a historical migration.

## Not allowed

Post-submit derivation/compilation/approval, checker execution, agent calls,
Celery cutover, ART, submission intake, or legacy self-committing approval.

## Acceptance

- Activate only `project.submission_artifact_policy.approve` for a human Project
  Manager with exact active project grant. Public service tokens deny.
- Approval requires UUID `Idempotency-Key`, dedicated PREP, exact OpenAPI action
  metadata, route-owned commit and fresh replay reauthorization.
- Lock order is project, draft guide, latest source snapshot, setup run,
  sufficiency report, target draft policy, current approved submission policy,
  current effective policy, current pre-submit policy, and any existing
  post-submit policy whose upstream lineage must be invalidated. All rows are
  revalidated against exact IDs/statuses/hashes/generation before consume. This
  is one total order: 12F3's post-agent relock, 12F4 approval, 12G derivation,
  approval/correction, and every overlapping mutation must acquire their shared
  lineage rows in this relative order with no alternate acquisition order.
- The authoritative sufficiency report must be for the exact snapshot and
  generation and be `passed`, or `passed_with_warnings` with that report's
  warnings acknowledged. Missing, blocked, stale, diagnostic-only, or
  unacknowledged-warning reports deny without mutation.
- Approval validates the non-bypassable Workstream default submission policy
  and compiles against one exact immutable default-catalogue snapshot. PREP,
  replay, and row provenance bind compiler and bundle schema versions,
  catalogue ID/version/schema, manifest SHA-256, ordered entry identities and
  configuration hashes, disabled-catalogue startup-config digest/IDs, compiled
  bundle hash, and downstream effective-plan hash when present. Stale compiler,
  changed catalogue/config, missing mandatory defaults, disabled mandatory
  definitions, or non-canonical bundles deny.
- One root transaction consumes approval PREP and atomically records: approved
  draft provenance, supersession of the prior upstream chain, new effective
  policy and hash, new compiled pre-submit policy and hash, replay completion,
  bounded allowed decision evidence, and local actor/link/grant/scope/action
  provenance on each protected row.
- Existing post-submit policy may only receive `lifecycle_status=superseded`,
  `superseded_at`, and the exact upstream replacement identity because its
  effective/pre-submit hash changed; that invalidation and its authority
  provenance commit in the approval transaction. 12F4 does not change its body,
  derive, compile, approve, enqueue or run post-submit/checker behavior. It may
  stage a bounded setup continuation identity that remains unusable until 12G.
- Exact replay returns the canonical effective result. Changed/pending/cross-
  action/link-substitution replay, stale/concurrent approval, revocation,
  wrong handle/session/transaction, and fault injection deny or roll back every
  product/replay/evidence mutation. Concurrent approvals create one current chain.
- Historical bootstrap rows remain readable and are never rewritten.

## Verification commands

```bash
cd backend
.venv/bin/ruff check app tests scripts
.venv/bin/pytest -q tests/test_authorization.py -k 'submission_artifact_policy and approve'
.venv/bin/pytest -q tests/test_projects.py -k 'submission_artifact_policy and (approve or effective or pre_submit or rollback or concurrent)'
.venv/bin/pytest -q tests/test_ci_test_lanes.py
.venv/bin/coverage erase
.venv/bin/coverage run --source=app.modules.projects,app.modules.authorization,app.modules.checkers --concurrency=greenlet -m pytest -q tests/test_authorization.py -k 'submission_artifact_policy and approve'
.venv/bin/coverage run --source=app.modules.projects,app.modules.authorization,app.modules.checkers --concurrency=greenlet --append -m pytest -q tests/test_projects.py -k 'submission_artifact_policy and (approve or effective or pre_submit or rollback or concurrent)'
.venv/bin/coverage report --include='app/modules/projects/submission_policy_mutation_*.py,app/modules/checkers/catalogue.py,app/modules/checkers/compiler.py,app/modules/checkers/effective_plan.py,app/modules/authorization/catalogue.py,app/modules/authorization/kernel.py,app/modules/authorization/prepared.py,app/modules/authorization/runtime.py' --precision=2 --fail-under=90
.venv/bin/python scripts/api_contract_e2e.py
cd ..
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

Every selector must be non-zero; exact pushed head passes Agent Gates and full
hosted Backend. Required reviewers: all L1 tracks. Human focus: lock order,
single-root atomicity, exact local provenance, and zero 12G behavior.
