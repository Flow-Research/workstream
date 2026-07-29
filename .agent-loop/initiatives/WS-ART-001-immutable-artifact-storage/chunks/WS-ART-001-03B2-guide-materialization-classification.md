# Chunk Contract: WS-ART-001-03B2 - Guide Materialization And Classification

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 03B1

## Goal

Materialize exact bound guide bytes through the fixed reader, independently
verify integrity, classify incidents, and detect formats in bounded private
scratch without extracting semantic content.

## Allowed Files

- ART guide-read port, canonical resources, materializer, incident records, and
  typed format detector/container inspector;
- extension of the existing `ArtifactMaterializationPort` convention and
  interface boundary; no parallel materialization abstraction;
- existing `ArtifactStore` and `ArtifactScratchManager` composition only;
- fixed startup limits for signatures, ZIP markers, entries, decompressed bytes,
  depth, ratio, image headers/dimensions, and read deadline;
- focused read, corruption, classification, container, cancellation, cleanup,
  authorization, and coverage tests; related docs/evidence.

## Not Allowed

- semantic extraction, parser dependencies, agent calls, arbitrary temp paths,
  direct provider access, generic download, Celery handles/bytes, legacy cutover,
  or AUTH availability edits.

## Acceptance Criteria

- fresh prepared `artifact.guide_source.read` authority is consumed before any
  provider read; the real kernel remains unavailable before AUTH-04B;
- test-only fixed authority proves positive read/materialization semantics while
  the composed live AUTH path proves deny-before-I/O until 04B;
- exact binding and setup generation are revalidated before and after full read;
- complete SHA-256 and byte count are recomputed into scratch and compared;
- missing, changed, truncated, unavailable, and stale reads record bounded ART
  incidents and never guide insufficiency;
- PDF, OOXML containers, CSV, Markdown, text, JSON, PNG/JPEG/WebP metadata,
  ordinary ZIP, ambiguous, and opaque input receive deterministic detection;
- audio/video declared types and signatures deterministically produce the
  unsupported outcome and never dispatch a parser;
- DOCX/PPTX/XLSX require bounded internal markers; symlinks, macros, external
  relationships, embedded executables, bombs, and malformed containers reject;
- cleanup occurs on success, denial, mismatch, cancellation, and timeout;
- changed subsystems remain at least 90% covered and repository coverage stays
  at least 78%.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_guide_artifacts.py tests/test_artifact_scratch_manager.py tests/test_guide_format_detection.py -q --cov=app.modules.artifacts --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
git diff --check
```

The exact PR head must pass hosted `Backend / test` and `Agent Gates / agent-gates`.

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.
