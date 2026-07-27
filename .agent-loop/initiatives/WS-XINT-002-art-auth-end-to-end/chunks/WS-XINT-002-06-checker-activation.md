# Chunk Contract: WS-XINT-002-06 Checker Authorization Activation

## Goal

Activate bounded pre/post-submit checker input and checker output/binding actions.

## Risk class

L1.

## Allowed files

```text
backend/app/modules/authorization/**
backend/app/modules/artifacts/authorization.py
backend/app/modules/artifacts/service.py
backend/app/modules/checkers/**
backend/tests/test_authorization.py
backend/tests/test_checker_materialization.py
backend/tests/test_checkers.py
docs/spec_authorization_service.md
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/**
```

## Not allowed

Human submission authority for checkers, Submission consumption, review
decisions, generic artifact reads, or new catalogue values.

## Acceptance criteria

- Pre-submit access binds the process-local admission generation, manifest,
  guide, policy, task, and checker definition; no scratch path is serialized.
- Post-submit access binds exact Submission, checker run, and immutable bindings.
- Output write and output binding are distinct fixed actions with exact generated
  commitment/run/role facts and separate evidence.
- Checker services cannot prepare/create/consume a Submission or access another
  admission/version.
- Revocation, action disablement, stale context, digest mismatch, replay, and
  cross-service attempts deny without product review outcomes.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_checker_materialization.py tests/test_checkers.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov=app.modules.checkers --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

The exact PR head must pass `Backend / test` and `Agent Gates / agent-gates`.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Byte minimization, service separation, exact context binding, and no product authority.
