# Chunk Contract: WS-ART-001-03B3B4 — Image Metadata Extractors

## Parent initiative

WS-ART-001 — Immutable Artifact Storage

## Goal

Install only the approved image dependency and expose bounded PNG/JPEG/WebP
structural metadata without OCR or raw pixels.
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
backend/app/modules/artifacts/guide_images.py
backend/app/modules/artifacts/guide_extraction.py
backend/app/modules/artifacts/guide_extraction_worker.py
backend/tests/test_guide_images.py
backend/tests/fixtures/guide_images/**
backend/tests/test_artifact_architecture.py
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/**
```

## Not allowed

OCR, pixel/base64 agent input, EXIF secrets/location propagation, transforms,
PDF/OOXML packages, framework/AUTH/Celery/submission changes.

## Acceptance criteria

- Exact 03B2 PNG/JPEG/WebP classification is required.
- Output is a fixed metadata schema and cannot satisfy required textual guide
  semantics.
- Parser imports and execution exist only in the isolated extraction child,
  never API, materialization/provider, AUTH, Celery, or agent assembly paths.
- Dimensions above 16,384 or 40 megapixels fail before decode/allocation.
- Malformed/truncated/decompression-bomb inputs, metadata privacy, crash,
  timeout, cancellation, cleanup, and coverage are proven.

## Verification commands

```bash
(cd backend && python scripts/check_guide_extractor_dependencies.py)
(cd backend && uv run ruff check app tests scripts)
(cd backend && uv run pytest -q tests/test_guide_images.py tests/test_guide_extraction.py)
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

Metadata minimization, dimension checks before allocation, decompression-bomb
behavior, and absence of OCR/raw pixels.
