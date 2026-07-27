# Chunk Contract: WS-XINT-002-08 End-to-End Conformance

## Goal

Prove that the complete ART lifecycle uses only the frozen catalogue and denies
every unauthorized, stale, replayed, or cross-boundary operation.

## Risk class

L1.

## Allowed files

```text
backend/app/modules/authorization/**
backend/app/modules/artifacts/**
backend/app/modules/tasks/**
backend/app/modules/checkers/**
backend/app/modules/reviews/**
backend/tests/**
backend/scripts/auth_api_e2e.py
backend/scripts/api_contract_e2e.py
scripts/check_stale_authorization_docs.py
scripts/check_stale_artifact_contracts.py
docs/spec_authorization_service.md
docs/spec_artifact_storage_service.md
docs/spec_review_lifecycle.md
docs/operations_artifact_storage.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/**
```

## Not allowed

New actions, permissions, identities, grants, lifecycle behavior, provider
redesign, or gate weakening.

## Acceptance criteria

- Generated parity covers every ART route/command, action/permission/owner,
  availability, resource type, service membership, and human/service isolation.
- Live proof covers guide ingest/use, initial and revision submission, checker
  remediation submission, human-review revision submission, checker input/output,
  reviewer packet/evidence, recovery, Operator reads/retry, and bounded audit behavior.
- Crossed proof covers actor/link/grant/assignment/lease revocation, action
  disablement, stale guide/policy/predecessor/version facts, concurrent consume,
  transaction replacement, evidence/participant/commit failure, timeout, and
  cancellation.
- Every durable mutation has atomic bounded decision evidence; no token, raw
  claim, byte content, scratch path, provider secret, or capability identity is
  persisted or logged.
- Stale scanners find no upload-session action, direct AUTH repository import
  from ART, generic download permission, token-role fallback, or alternate
  capability path.
- Focused tests and API drill pass locally; full backend coverage and migration
  matrix pass in GitHub Actions without weakening the 78/90 percent gates.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_artifact_recovery.py tests/test_submission_concurrency.py tests/test_checkers.py tests/test_review_artifacts.py tests/test_review_revision.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov=app.modules.tasks --cov=app.modules.checkers --cov=app.modules.reviews --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python scripts/api_contract_e2e.py)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/python scripts/auth_api_e2e.py)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

The exact PR head must pass `Backend / test` and `Agent Gates / agent-gates`,
preserving the 78 percent global and 90 percent materially changed subsystem floors.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Complete matrix coverage, privacy, revocation races, and proof that no new AUTH
dependency was discovered after chunk 02.
