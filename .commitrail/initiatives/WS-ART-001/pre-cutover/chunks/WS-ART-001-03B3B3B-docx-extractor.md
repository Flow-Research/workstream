# Chunk Contract: WS-ART-001-03B3B3B — DOCX Extractor

## Parent initiative

WS-ART-001 — Immutable Artifact Storage

## Goal

Add deterministic bounded DOCX text/structure extraction using only the approved OOXML capability.

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
backend/app/modules/artifacts/guide_docx.py
backend/app/modules/artifacts/guide_extraction.py
backend/app/modules/artifacts/guide_extraction_service.py
backend/app/modules/artifacts/guide_extraction_worker.py
backend/scripts/run_test_lanes.py
backend/tests/test_artifact_architecture.py
backend/tests/test_guide_docx.py
backend/tests/test_guide_extraction.py
backend/tests/test_guide_bindings.py
backend/tests/fixtures/guide_docx/**
backend/tests/fixtures/guide_extraction_probe_worker.py
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/**
```

## Not allowed

PPTX/XLSX behavior, package additions beyond approved lock, framework/AUTH/Celery/submission changes.

## Acceptance criteria

- Require exact DOCX classification and the shared OOXML security boundary.
- Traverse body elements in document order. Emit paragraph text in run order;
  emit each table in row then cell order, flattening nested tables at their
  containing-cell position with fixed row/cell separators. Headers, footers,
  comments, tracked-deletion text, and embedded objects are omitted and
  recorded in omission facts. Streaming stops with `limit_exceeded` before
  exceeding D42's 4 MiB canonical-output limit; no partial result is usable.
- Canonical DOCX output is compact sorted JSON with one `blocks` array. A
  paragraph block is `{"type":"paragraph","text":"..."}`. A table block is
  `{"type":"table","text":"..."}` with tab between cells, newline between
  rows, newline between multiple paragraphs in a cell, and a newline on each
  side of a nested table when adjacent cell content exists. Empty paragraphs,
  rows, and cells remain explicit. `w:t` and visible field-result text are
  retained; `w:tab` becomes tab and `w:br|w:cr` becomes newline. Hyperlink
  display text stays in document order. Field instructions, hidden text,
  comment markers, tracked deletions, drawings, pictures, and other passive
  non-text body objects are omitted. Active embedded package content remains a
  malformed OOXML rejection before DOCX extraction. Traversal deeper than 64
  nested document/container levels returns stable `malformed` evidence.
- Successful DOCX omission facts have the fixed bounded boolean schema
  `truncated`, `omitted`, `headers`, `footers`, `comments`,
  `tracked_deletions`, `embedded_objects`, `hidden_text`, and
  `field_instructions`. The existing isolated-child result protocol carries these
  facts; other formats retain the exact default
  `{"truncated":false,"omitted":false}`. Persistence binds and replay-checks
  omission facts with the canonical output. DOCX uses exact policy identity
  `guide-extraction-v3`, so obsolete unsupported evidence cannot replay.
- Import the parser only in the isolated child and prove deterministic output,
  malformed/unsafe input, exact output boundary, crash, timeout, cancellation,
  cleanup, approval-gate, and coverage behavior.
- Assign the focused DOCX test module to an existing canonical hosted semantic
  lane without changing lane or coverage policy.

## Verification commands

```bash
(cd backend && uv run ruff check app tests)
(cd backend && uv run python scripts/check_guide_extractor_dependencies.py)
(cd backend && uv run pytest -q tests/test_guide_ooxml.py tests/test_guide_docx.py tests/test_guide_extraction.py tests/test_guide_bindings.py tests/test_artifact_architecture.py)
(cd backend && uv run pytest -q tests/test_guide_docx.py --cov=app.modules.artifacts.guide_docx --cov-report=term-missing --cov-fail-under=90)
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
