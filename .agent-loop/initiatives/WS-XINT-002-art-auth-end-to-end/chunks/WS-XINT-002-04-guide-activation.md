# Chunk Contract: WS-XINT-002-04 Guide Authorization Activation

## Goal

Activate guide ingest after ART-03A evidence, then guide binding/read after
ART-03B evidence, without weakening the ART-03C clean cut.

## Risk class

L1.

## Allowed files

```text
backend/app/modules/authorization/**
backend/app/modules/artifacts/authorization.py
backend/app/modules/artifacts/service.py
backend/app/modules/projects/**
backend/tests/test_authorization.py
backend/tests/test_guide_artifacts.py
backend/tests/test_artifact_admission.py
docs/spec_authorization_service.md
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/**
```

## Not allowed

Submission/review behavior, provider redesign, token roles, generic guide
download, or new catalogue values.

## Acceptance criteria

- Ingest requires an exact Project Manager grant and locks actor/link, project,
  draft guide, snapshot/item, policy generation, request digest, and operation.
- Final PREP consumption occurs before capacity/put intent commit and provider
  I/O; revoke/stale/cross-project/replay cases deny atomically.
- Guide binding/read use separate fixed identities and exact verified content,
  binding role, guide item, and setup generation.
- Activation is split at the 03A/03B evidence boundary if both manifests are not
  already merged; no later action is enabled early.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<test-db> .venv/bin/pytest tests/test_authorization.py tests/test_guide_artifacts.py tests/test_artifact_admission.py -q --cov=app.modules.authorization --cov=app.modules.artifacts --cov=app.modules.projects --cov-report=term-missing --cov-fail-under=90)
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

Manager-only ingest, separate service authority, exact generations, and clean cut.
