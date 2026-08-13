# Chunk Contract: WS-ARCH-001-02H — AUTH Submission Consumption Activation

## Merge state

- Outcome on merge: `complete`

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Activate the exact fresh human Submission-consumption and fixed ART binding
service authority required by the merged hidden 02F transaction.

## Why this chunk exists

Human Submission authority never implies fixed binding-service authority, and
availability must be reviewed independently from feature persistence.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Entry gate

WS-ARCH-001-02G is merged, and AUTH verifies the 02D preparation, 02E
admission/binding, and 02F transaction manifests against current `main`.

## Allowed files

```text
backend/app/modules/authorization/api/**
backend/app/modules/authorization/**/submission*.py
backend/app/modules/authorization/submission_consumption.py
backend/app/modules/authorization/submission_creation_authorization.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/artifact_project_authority.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/adapters/auth/**
backend/app/adapters/tasks/__init__.py
backend/app/adapters/artifacts/__init__.py
backend/app/api/deps/authorization.py
backend/app/modules/artifacts/authorization.py
backend/app/modules/tasks/api/submission_command.py
backend/app/modules/tasks/submission_composition.py
backend/app/main.py
backend/alembic/versions/<next-current-main-revision>.py
backend/tests/test_authorization.py
backend/tests/test_submission_composition.py
backend/tests/test_submission_preparation_authorization.py
backend/tests/test_artifact_bindings.py
backend/tests/test_artifact_bindings_db.py
backend/tests/authorization/test_fixed_service_action_context.py
backend/tests/architecture/test_authorization_boundary.py
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/STATUS.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/CHUNK_MAP.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-02H-auth-consumption-activation.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02H-consumption-activation.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/reviews/WS-ARCH-001-02H-external-review-response.md
docs/spec_authorization_service.md
docs/operations_authorization_service.md
docs/roadmap_status.md
```

## Not allowed

Preparation, revision, checker, review, contribution, or generic download
authority; new action/permission/service identity; public route changes; ART or
TASK persistence; human substitution for fixed service authority.

## Acceptance criteria

- [ ] Fresh human `submission.create` and fixed-service
      `artifact.submission.binding.create -> artifact.binding.create` are
      independently evaluated and transaction-bound to the exact merged facts.
- [ ] Wrong/revoked actor, link, grant, assignment, service identity, action,
      session, transaction, admission, predecessor or policy context denies.
- [ ] Authorization evidence commits atomically with the 02F protected
      transaction; no capability is serializable or reusable.
- [ ] Live hidden-path PostgreSQL tests prove one complete Submission, binding,
      admission transition, and authorization evidence effect under concurrent
      consumption; denial/cancellation/persistence failure produces zero effect.
- [ ] No adjacent action becomes available and the public route remains
      unchanged until 02I.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/authorization app/modules/artifacts/authorization.py app/modules/tasks/api/submission_command.py app/modules/tasks/submission_composition.py app/adapters/auth app/adapters/tasks app/adapters/artifacts app/api/deps/authorization.py app/main.py tests/test_authorization.py tests/test_submission_composition.py tests/test_submission_preparation_authorization.py tests/test_artifact_bindings.py tests/test_artifact_bindings_db.py tests/authorization/test_fixed_service_action_context.py tests/architecture/test_authorization_boundary.py)
(cd backend && export WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set WORKSTREAM_TEST_DATABASE_URL}" && .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_submission_composition.py tests/test_submission_preparation_authorization.py tests/test_artifact_bindings.py tests/test_artifact_bindings_db.py tests/authorization/test_fixed_service_action_context.py tests/architecture/test_authorization_boundary.py --cov=app.modules.authorization --cov-fail-under=90)
(cd backend && export WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set WORKSTREAM_TEST_DATABASE_URL}" && .venv/bin/python -m pytest -q tests/test_artifact_bindings.py tests/test_artifact_bindings_db.py tests/test_submission_composition.py --cov=app.modules.artifacts --cov-fail-under=90)
(cd backend && export WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set WORKSTREAM_TEST_DATABASE_URL}" && .venv/bin/python -m pytest -q tests/test_submission_composition.py --cov=app.modules.tasks --cov-fail-under=90)
gh pr checks <PR-number> --watch
(cd backend && .venv/bin/python -m scripts.test_structure_boundary validate --policy ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_POLICY.md --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json)
python3 scripts/check_stale_authorization_docs.py
(cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main)
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
docs, reuse/dedup, and test delta.

## Human review focus

Dual authority, least privilege, exact resource binding, and confirmation that
the live API did not change.

## Stop conditions

Stop if 02G is absent or its manifest differs, a new catalogue value is needed,
or fixed service authority would be inherited from the contributor.
