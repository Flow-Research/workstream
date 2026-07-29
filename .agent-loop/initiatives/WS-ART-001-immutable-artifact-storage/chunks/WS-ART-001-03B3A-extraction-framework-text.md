# Chunk Contract: WS-ART-001-03B3A - Extraction Framework And Text Formats

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 03B2

## Goal

Prove the isolated extraction framework, canonical content/usage provenance,
and standard-library text, Markdown, JSON, and CSV extraction.

## Allowed Files

- typed extraction capability/registry and explicit composition entries;
- isolated no-network subprocess and versioned extraction policy;
- content-derived extraction and binding/generation usage models, one migration,
  repository, and schemas;
- focused isolation, limit, cancellation, cleanup, determinism, provenance,
  text/Markdown/JSON/CSV, and coverage tests; related docs/evidence.

## Not Allowed

- production parser dependencies, PDF/OOXML/image parsing, plugin discovery,
  in-process untrusted parsing, provider writes/access, agent invocation, OCR,
  audio/video, legacy cutover, or AUTH availability edits.

## Acceptance Criteria

- no-network subprocess enforces input/output, CPU/time/memory, row/cell,
  encoding, nesting, cancellation, and cleanup limits;
- extraction revalidates exact 03B2 digest/binding/format/policy provenance;
- deterministic content records are keyed by content, format, extractor/version,
  and policy; separate usage records name item, binding, run, and generation;
- text/Markdown/JSON/CSV canonicalization and error statuses are deterministic;
- unsupported raw input never reaches an agent or provider write;
- changed subsystem coverage is at least 90%; repository coverage stays 78%.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_guide_extraction.py -q --cov=app.modules.artifacts.guide_extraction --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
git diff --check
```

The exact PR head must pass hosted `Backend / test` and `Agent Gates / agent-gates`.
Every changed production module, including repository, schema, migration-owned
service, and composition surfaces, must be included in a dedicated retained
90% coverage report or an explicitly reviewed existing subsystem report.

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.
