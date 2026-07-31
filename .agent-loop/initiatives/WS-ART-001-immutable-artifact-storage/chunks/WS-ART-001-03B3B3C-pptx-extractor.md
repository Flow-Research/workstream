# Chunk Contract: WS-ART-001-03B3B3C — PPTX Extractor

## Parent initiative

WS-ART-001 — Immutable Artifact Storage

## Goal

Add deterministic bounded PPTX slide and notes extraction using only the approved OOXML capability.

`WS-ART-001-03B3B1` and `WS-ART-001-03B3B3A` are hard predecessors. Package
installation and imports fail closed unless the merged protected GitHub approval baseline matches
the exact pinned allowlist.

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

- Require exact PPTX classification and the shared OOXML security boundary.
- Accept exactly 300 slides and reject 301 before extraction. Traverse slides
  by presentation order, shapes by XML document order, and text paragraphs/runs
  in document order; append speaker notes after their owning slide in notes XML
  order. Omit masters, comments, hidden metadata, and embedded objects while
  recording omission facts. Exceeding D42's output limit produces unusable
  `limit_exceeded`, never partial agent input.
- Prove deterministic slide/notes output, unsafe/malformed input, child-only
  imports, exact 300/301 and output boundaries, crash, timeout, cancellation,
  cleanup, approval-gate, and coverage behavior.

## Verification commands

```bash
(cd backend && uv run ruff check app tests)
(cd backend && python scripts/check_guide_extractor_dependencies.py)
(cd backend && uv run pytest -q tests/test_guide_ooxml.py tests/test_guide_pptx.py tests/test_guide_extraction.py --cov=app.modules.artifacts --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

Hosted Backend/Agent Gates must preserve 90% changed-subsystem and 78% repository coverage.

## Required reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human review focus

Format-specific deterministic semantics, reuse of the shared secure container
boundary, exact limits, and absence of parser imports outside the isolated child.

## Stop conditions

Stop on unapproved dependencies, scope expansion, isolation/CI weakening,
architecture drift, or repeated repair failure.
