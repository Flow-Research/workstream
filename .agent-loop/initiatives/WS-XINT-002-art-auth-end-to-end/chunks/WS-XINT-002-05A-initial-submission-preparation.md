# Chunk Contract: WS-XINT-002-05A Initial Submission Preparation

## Goal

Activate one-ZIP preparation through one durable ready admission for an initial submission.

## Risk class

L1.

## Allowed files

```text
backend/app/modules/authorization/**
backend/app/modules/artifacts/authorization.py
backend/app/modules/artifacts/service.py
backend/app/modules/artifacts/repository.py
backend/app/modules/artifacts/router.py
backend/app/modules/artifacts/schemas.py
backend/app/modules/tasks/service.py
backend/app/modules/tasks/repository.py
backend/tests/test_authorization.py
backend/tests/test_submission_bundle_admission.py
backend/tests/test_submission_concurrency.py
docs/spec_authorization_service.md
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/**
```

## Not allowed

Submission creation/binding, revisions, reviewer behavior, upload sessions,
provider I/O before committed intent, compatibility aliases, or new catalogue values.

## Acceptance criteria

- Require exact active assignment, task/project, no predecessor, locked
  guide/policy/checker context, request digest, operation generation, and key.
- Consume final prepared authority before capacity/put intent and provider I/O.
- Revoked, stale, cross-project, replayed, and concurrent attempts create no
  partial or duplicate ready admission; denial evidence is atomic and concealed.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_submission_bundle_admission.py tests/test_submission_concurrency.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

The exact PR head must pass `Backend / test` and
`Agent Gates / agent-gates`, preserving the 78 percent global and 90 percent
materially changed subsystem coverage floors.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Assignment scope, final revalidation, provider-I/O ordering, and admission uniqueness.
