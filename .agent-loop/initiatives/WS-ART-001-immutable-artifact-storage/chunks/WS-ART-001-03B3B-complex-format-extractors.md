# Chunk Contract: WS-ART-001-03B3B - Complex Format Extractors

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 03B3A; dependency approval required

## Goal

Add approved PDF, DOCX, PPTX, XLSX, and PNG/JPEG/WebP metadata adapters on the
already-proven isolated framework.

## Entry Gate

The human owner explicitly approves an exact pinned dependency allowlist after
review of license, maintenance, advisories, transitive graph, malformed-input
history, and cancellation behavior. The PR includes the package/lock diff,
machine-readable allowlist, dependency-tree evidence, license evidence, and
security-review record. CI fails if a parser dependency is outside that list.

## Allowed Files

- one typed adapter per approved format and explicit registry entries;
- approved package/lock/allowlist and deterministic dependency gate;
- bounded fixtures and format-confusion, macro/external relationship, embedded
  content, page/slide/sheet/cell/image, parser crash, timeout, and coverage tests;
- related docs/evidence.

## Not Allowed

- framework redesign, runtime plugins/fallbacks, OCR, audio/video, ordinary ZIP
  semantics, raw pixels/base64 to agents, provider writes/access, legacy cutover,
  or AUTH availability edits.

## Acceptance Criteria

- exact 03B2 classification provenance is required before parser execution;
- all parsers stay inside the 03B3A isolation/limit/cancellation boundary;
- PDF rejects more than 500 pages; PPTX rejects more than 300 slides; XLSX
  rejects more than 100 sheets, 100,000 rows, 1,000,000 cells, or 32,768
  characters in one cell; images reject more than 40 megapixels or 16,384
  pixels on either dimension; every breach records `limit_exceeded`;
- tests cover each exact boundary and one-over boundary, malformed containers,
  parser crash, timeout, cancellation, cleanup, and executor loss without a
  partial extraction or usage record;
- OOXML markers distinguish formats and reject macros, external relationships,
  embedded executables, bombs, and ambiguity;
- PNG/JPEG/WebP output is metadata only and cannot satisfy required text;
- parser dependency allowlist and lock graph are deterministic and CI-enforced;
- changed subsystem coverage is at least 90%; repository coverage stays 78%.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && .venv/bin/python scripts/check_guide_extractor_dependencies.py)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_guide_format_detection.py tests/test_guide_extraction.py -q --cov=app --cov-report=term-missing --cov-fail-under=0)
(cd backend && .venv/bin/coverage report --precision=2 --fail-under=78)
(cd backend && .venv/bin/coverage report --include='app/modules/artifacts/*,app/core/config.py,app/interfaces/artifacts.py' --precision=2 --fail-under=90)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
git diff --check
```

The exact PR head must pass hosted `Backend / test` and `Agent Gates / agent-gates`.
Every changed production module, including adapter registry, dependency gate,
configuration, and composition surfaces, must be included in a dedicated
retained 90% coverage report or an explicitly reviewed existing subsystem report.

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.
