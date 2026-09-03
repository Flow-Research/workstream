# Chunk Contract: WS-ART-001-03B3B2 — PDF Extractor

## Parent initiative

WS-ART-001 — Immutable Artifact Storage

## Goal

Install only the approved PDF dependency and add bounded PDF text extraction on
the existing 03B3A isolated framework.

`WS-ART-001-03B3B1` is a hard predecessor. Installation and imports fail
closed unless its merged protected GitHub approval baseline matches the exact pinned allowlist.
## Approved plan reference

- PLAN: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/CHUNK_MAP.md`

## Risk class

L1

## SLA

P2

## Allowed files

```text
backend/pyproject.toml
backend/uv.lock
backend/config/guide_extractor_dependencies.json
backend/app/modules/artifacts/guide_pdf.py
backend/app/modules/artifacts/guide_extraction.py
backend/app/modules/artifacts/guide_extraction_worker.py
backend/app/modules/artifacts/guide_extraction_service.py
backend/scripts/run_test_lanes.py
backend/tests/test_guide_pdf.py
backend/tests/test_guide_bindings.py
backend/tests/test_guide_extraction.py
backend/tests/fixtures/guide_pdf/**
backend/tests/test_artifact_architecture.py
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/**
```

## Not allowed

OOXML/image packages, framework redesign, OCR, JavaScript/actions, external
fetches, provider/AUTH/Celery/submission changes.

## Acceptance criteria

- Exact 03B2 PDF classification is required.
- PDF uses a new policy identity so pre-support `unsupported` attempts cannot
  replay; an exact-lineage retry budget safely resets for that policy change.
- The new focused PDF test module is assigned to an existing canonical hosted
  semantic lane without changing lane or coverage policy.
- Encrypted, malformed, attachments, embedded files, forms, XFA, launch/open
  actions, active/external, and over-500-page PDFs fail with bounded outcomes.
- Parser imports and execution exist only in the isolated extraction child,
  never API, materialization/provider, AUTH, Celery, or agent assembly paths.
- No network, filesystem escape, partial usage, or raw binary reaches agents.
- Exact 500/501 page, timeout, crash, cancellation, cleanup, and coverage proof.

## Verification commands

```bash
(cd backend && uv run python scripts/check_guide_extractor_dependencies.py)
(cd backend && uv run ruff check app tests scripts)
(cd backend && uv run pytest -q tests/test_guide_pdf.py tests/test_guide_extraction.py tests/test_artifact_architecture.py)
(cd backend && uv run pytest -q tests/test_guide_pdf.py --cov=app.modules.artifacts.guide_pdf --cov-report=term-missing --cov-fail-under=90)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 600 -- .venv/bin/python -m pytest -q tests/test_guide_bindings.py::test_pdf_support_replaces_the_obsolete_policy_budget_without_replay))
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

Hosted Backend/Agent Gates must preserve 90% changed-subsystem and 78% repository coverage.

## Required reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Stop conditions

Stop if scope expands, a dependency lacks approval/evidence, isolation must be
weakened, CI or coverage must be weakened, or a second runtime parser path is
required.

## Human review focus

PDF parser graph, active-content handling, page-bound enforcement, deterministic
canonical text, and isolation.
