# Chunk Contract: WS-ART-001-03B3B3A — OOXML Container Security

## Parent initiative

WS-ART-001 — Immutable Artifact Storage

## Goal

Add shared bounded ZIP/XML marker and rejection capabilities without extracting DOCX, PPTX, or XLSX content.

## Approved plan reference

- PLAN: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/CHUNK_MAP.md`

## Risk class

L1

## SLA

P2

## Allowed files

```text
backend/app/modules/artifacts/guide_ooxml.py
backend/app/modules/artifacts/guide_extraction_worker.py
backend/tests/test_guide_ooxml.py
backend/tests/fixtures/guide_ooxml/**
backend/pyproject.toml
backend/uv.lock
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/**
```

## Not allowed

No document adapter/registry activation, generic ZIP semantics, AUTH/Celery/submission changes.

## Acceptance criteria

- Require exact classification; reject ambiguity, macros, external relationships, embedded executables, traversal, bombs, unsafe XML and undeclared parser imports. Parser imports execute only in the isolated child. Prove limits, crash, timeout, cancellation, cleanup and dependency gate.

## Verification commands

```bash
(cd backend && uv run ruff check app tests)
(cd backend && python scripts/check_guide_extractor_dependencies.py)
(cd backend && uv run pytest -q tests/test_guide_ooxml.py)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human review focus

Format-specific deterministic semantics, reuse of the shared secure container
boundary, exact limits, and absence of parser imports outside the isolated child.

## Stop conditions

Stop on unapproved dependencies, scope expansion, isolation/CI weakening,
architecture drift, or repeated repair failure.

