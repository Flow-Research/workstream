# Chunk Contract: WS-ART-001-03B3B3A — OOXML Container Security

## Parent initiative

WS-ART-001 — Immutable Artifact Storage

## Goal

Add shared bounded ZIP/XML marker and rejection capabilities without extracting DOCX, PPTX, or XLSX content.

`WS-ART-001-03B3B1` is a hard predecessor. Package installation and parser
imports fail closed unless its merged protected GitHub approval baseline matches the exact pinned
allowlist. The DOCX, PPTX, and XLSX chunks inherit this same gate.

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
backend/app/modules/artifacts/guide_formats.py
backend/app/modules/artifacts/guide_extraction_worker.py
backend/scripts/run_test_lanes.py
backend/tests/test_guide_ooxml.py
backend/tests/test_guide_extraction.py
backend/tests/test_artifact_architecture.py
backend/tests/test_guide_extractor_dependencies.py
backend/tests/fixtures/guide_ooxml/**
backend/pyproject.toml
backend/uv.lock
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/**
```

## Not allowed

No document adapter/registry activation, generic ZIP semantics, AUTH/Celery/submission changes.

## Acceptance criteria

- Inspect central-directory metadata before reading entry bodies. Reject
  duplicate/case-colliding normalized names, absolute/traversing names,
  encrypted entries, nested archives, symlinks/special entries, macros,
  external relationships, embedded objects/executables, DTD/entity use, and
  any required marker conflict. Extra members are allowed only when their
  normalized names fall within the fixed OPC package-part allowlist documented
  in the implementation; unknown roots or executable-capable suffixes reject
  before a format adapter runs.
- Inherit the fixed D42 limits: at most 2,000 entries, 128 MiB decompressed
  bytes, nesting depth 8, 32 MiB input, 4 MiB output, 30 CPU seconds, 60 wall
  seconds, 512 MiB address space, 32 descriptors, and no child processes/core
  dumps. Each breach has the D42 bounded outcome before adapter dispatch.
- Require exact classification and reject ambiguity. Parser imports execute
  only in the isolated child. Prove every rejection class and boundary plus
  crash, timeout, cancellation, cleanup, and the dependency gate.
- Assign the new focused test module to an existing canonical hosted semantic
  lane without changing lane or coverage policy.

## Verification commands

```bash
(cd backend && uv run ruff check app tests)
(cd backend && uv run python scripts/check_guide_extractor_dependencies.py)
(cd backend && uv run pytest -q tests/test_guide_ooxml.py tests/test_guide_extraction.py tests/test_artifact_architecture.py)
(cd backend && uv run pytest -q tests/test_guide_ooxml.py --cov=app.modules.artifacts.guide_ooxml --cov-report=term-missing --cov-fail-under=90)
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
