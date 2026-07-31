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
backend/scripts/run_test_lanes.py
backend/tests/test_artifact_architecture.py
backend/tests/test_guide_bindings.py
backend/tests/test_guide_extraction.py
backend/tests/test_guide_pptx.py
backend/tests/fixtures/guide_pptx/**
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/**
```

## Not allowed

DOCX/XLSX behavior, unapproved packages, framework/AUTH/Celery/submission changes.

## Acceptance criteria

- Require exact PPTX classification and the shared OOXML security boundary.
- Use exact policy identity `guide-extraction-v4`; obsolete `unsupported` or
  older PPTX evidence cannot replay as current-policy success. The parent
  result protocol accepts successful PPTX evidence only with the exact boolean
  omission keys `truncated`, `omitted`, `masters`, `comments`,
  `hidden_metadata`, `non_text_objects`, and `embedded_objects`.
  `truncated=false`; `omitted` is true exactly when any category is true.
  Persistence and replay comparison bind the complete omission mapping to the
  same canonical output.
- Emit compact sorted JSON with one `slides` array. Each entry has the exact
  shape `{"notes":[...],"number":N,"text":[...]}`. `number` is the
  one-based presentation position. `text` contains one string per DrawingML
  `a:p` in slide shape-tree XML order, with `a:t` run text concatenated in XML
  order, `a:tab` represented as tab, and `a:br` represented as newline.
  Hyperlink display text and placeholder text remain visible. Grouped shapes
  recurse in XML order; table paragraphs follow table row/cell XML order.
  Empty text-bearing paragraphs, empty slides, and empty notes remain explicit.
  Pictures, charts, diagrams, media, OLE/package objects, alt text, and other
  non-text drawing metadata never enter canonical output.
- `notes` uses the same paragraph/run rules and follows notes shape-tree XML
  order. Notes placeholders of type `hdr`, `ftr`, `dt`, `sldNum`, and `sldImg`
  are metadata and are omitted; body/object notes and ordinary text shapes are
  retained. Notes are embedded only in their owning slide entry, never emitted
  as an independent slide.
- `ppt/presentation.xml` `p:sldIdLst` is the sole slide-order authority. Resolve
  each `r:id` through `ppt/_rels/presentation.xml.rels` using the exact passive
  Transitional
  `http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide`
  or Strict `http://purl.oclc.org/ooxml/officeDocument/relationships/slide`
  relationship type. Resolve an optional notes slide through that slide's
  `.rels` using the corresponding exact Transitional or Strict `notesSlide`
  URI; a package may not mix those relationship namespaces. Resolve
  case-variant stored part names through the validator-approved case-folded
  map. Missing/dangling/duplicate IDs or targets, cross-root/type mismatches,
  one notes part owned by multiple slides, and orphan slide or notes parts fail
  `malformed/pptx_relationship_conflict`; they are never silently omitted.
- Accept exactly 300 ordered slides and reject 301 before slide/notes extraction
  with `limit_exceeded/pptx_slide_limit`. Missing/unreadable presentation parts
  use `malformed/pptx_presentation_unavailable`. Non-well-formed or unsafe XML
  is rejected first by the shared boundary as `malformed/ooxml_unsafe_xml`;
  well-formed invalid presentation roots use
  `malformed/pptx_invalid_presentation_xml`, invalid slide roots use
  `malformed/pptx_invalid_slide_xml`, and invalid notes roots use
  `malformed/pptx_invalid_notes_xml`. Invalid relationship XML or ownership
  remains `malformed/pptx_relationship_conflict`. Reject traversal beyond 64
  nested shape/text/container levels as
  `malformed/pptx_nesting_limit`. Exceeding D42's exact 4 MiB output limit produces unusable
  `limit_exceeded/output_limit`, never partial agent input.
- Successful omission facts record master/handout/notes-master parts,
  comment/comment-author parts, hidden document/custom/alt/visibility metadata,
  and passive non-text drawing objects. Active embedded content remains a
  shared OOXML malformed rejection before PPTX extraction.
- Prove deterministic slide/notes output, unsafe/malformed input, child-only
  imports, exact relationship/orphan handling, 300/301, depth and output
  boundaries, crash, timeout, cancellation, cleanup, approval-gate, complete
  cross-process omission facts, v4 persistence/replay identity, and coverage
  behavior. Assign the focused PPTX module to the existing canonical hosted
  semantic lane without changing lane or coverage policy.

## Verification commands

```bash
(cd backend && uv run ruff check app tests)
(cd backend && python scripts/check_guide_extractor_dependencies.py)
(cd backend && uv run pytest -q tests/test_guide_ooxml.py tests/test_guide_pptx.py tests/test_guide_extraction.py tests/test_guide_bindings.py tests/test_artifact_architecture.py tests/test_ci_test_lanes.py)
(cd backend && uv run pytest -q tests/test_guide_pptx.py --cov=app.modules.artifacts.guide_pptx --cov-report=term-missing --cov-fail-under=90)
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
