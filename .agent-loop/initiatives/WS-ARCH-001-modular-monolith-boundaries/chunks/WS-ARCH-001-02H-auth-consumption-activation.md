# Chunk Contract: WS-ARCH-001-02H — AUTH Submission Consumption Activation

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
backend/app/adapters/auth/**
backend/alembic/versions/<next-current-main-revision>.py
backend/tests/test_authorization.py
backend/tests/test_submission_concurrency.py
backend/tests/architecture/test_authorization_boundary.py
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/**
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/**
docs/spec_authorization_service.md
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
(cd backend && .venv/bin/python -m ruff check app/modules/authorization app/adapters/auth tests/test_authorization.py)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_submission_concurrency.py tests/architecture/test_authorization_boundary.py --cov=app.modules.authorization --cov-fail-under=90)
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
