# Chunk Contract: WS-ART-001-03B3B3C — PPTX Extractor

## Parent initiative

WS-ART-001 — Immutable Artifact Storage

## Goal

Add deterministic bounded PPTX slide and notes extraction using only the approved OOXML capability.

## Approved plan reference

- PLAN: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/CHUNK_MAP.md`

## Risk class

L1

## SLA

P2

## Allowed files

```text
backend/app/modules/artifacts/guide_pptx.py
backend/app/modules/artifacts/guide_extraction.py
backend/app/modules/artifacts/guide_extraction_worker.py
backend/tests/test_guide_pptx.py
backend/tests/fixtures/guide_pptx/**
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/**
```

## Not allowed

DOCX/XLSX behavior, unapproved packages, framework/AUTH/Celery/submission changes.

## Acceptance criteria

- Require exact PPTX classification; prove 300/301 slides, deterministic slide/notes order, unsafe OOXML rejection, child-only imports, malformed, crash, timeout, cancellation, cleanup and coverage.

## Verification commands

```bash
(cd backend && uv run ruff check app tests)
(cd backend && python scripts/check_guide_extractor_dependencies.py)
(cd backend && uv run pytest -q tests/test_guide_ooxml.py tests/test_guide_pptx.py tests/test_guide_extraction.py)
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
