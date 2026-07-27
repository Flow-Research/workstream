# Chunk Contract: WS-XINT-002-03 Internal Service Activation

## Goal

Activate only `artifact.verification.execute`, `artifact.pending_work.scan`, and
`artifact.put_attempt.resolve` against merged ART recovery facts.

## Risk class

L1.

## Allowed files

```text
backend/app/modules/authorization/**
backend/app/modules/artifacts/authorization.py
backend/app/modules/artifacts/service.py
backend/app/**/artifacts.py
backend/tests/test_authorization.py
backend/tests/test_artifact_verification.py
backend/tests/test_artifact_recovery.py
backend/tests/test_artifact_put_resolution.py
docs/operations_artifact_storage.md
docs/spec_authorization_service.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/**
```

## Not allowed

Human grants, provider semantics, Operator retry execution, other action
activation, or new catalogue values.

## Acceptance criteria

- Each fixed identity can execute only its matrix action against one exact job,
  scan page, or put attempt and execution fence.
- Profile/link revocation, wrong identity, wrong action, stale fence, duplicate
  lease, and concurrent execution deny before durable ART mutation.
- Decision evidence and lease/state mutation commit atomically; provider I/O
  begins only after durable intent.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_artifact_verification.py tests/test_artifact_recovery.py tests/test_artifact_put_resolution.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov-report=term-missing --cov-fail-under=90)
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

Service least privilege, recovery ownership, provider-I/O ordering, and replay.
