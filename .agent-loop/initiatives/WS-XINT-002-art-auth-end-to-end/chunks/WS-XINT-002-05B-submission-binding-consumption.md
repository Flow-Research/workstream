# Chunk Contract: WS-XINT-002-05B Submission Binding Consumption

## Goal

Activate fresh human Submission creation and separate fixed artifact binding in
one exactly-once ready-admission transaction.

## Risk class

L1.

## Allowed files

```text
backend/app/modules/authorization/**
backend/app/modules/artifacts/authorization.py
backend/app/modules/artifacts/service.py
backend/app/modules/artifacts/repository.py
backend/app/modules/tasks/**
backend/tests/test_authorization.py
backend/tests/test_submission_api.py
backend/tests/test_submission_concurrency.py
backend/tests/test_submission_history.py
docs/spec_authorization_service.md
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/**
```

## Not allowed

Revision obligations, checker/reviewer lifecycle changes, provider calls from
product modules, compatibility paths, or new catalogue values.

## Acceptance criteria

- Consume fresh human `submission.create` and independent fixed
  `artifact.submission.binding.create` capabilities in one transaction.
- Lock exact admission/task/assignment/context/content, create one immutable
  Submission/binding, consume admission, and commit once.
- Wrong/revoked/stale/cross-resource/replayed/concurrent attempts create zero or
  exactly one complete result; denial precedes admission-state disclosure.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_submission_api.py tests/test_submission_concurrency.py tests/test_submission_history.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov=app.modules.tasks --cov-report=term-missing --cov-fail-under=90)
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

Dual authority, one transaction, concealment, and exactly-once creation.
