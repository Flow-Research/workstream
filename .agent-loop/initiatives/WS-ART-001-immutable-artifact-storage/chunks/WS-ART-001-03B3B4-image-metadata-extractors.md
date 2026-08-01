# Chunk Contract: WS-ART-001-03B3B4 — Image Metadata Extractors

## Parent initiative

WS-ART-001 — Immutable Artifact Storage

## Goal

Install only the approved image dependency and expose bounded PNG/JPEG/WebP
structural metadata without OCR or raw pixels.

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
backend/app/modules/artifacts/guide_images.py
backend/app/modules/artifacts/guide_extraction.py
backend/app/modules/artifacts/guide_extraction_worker.py
backend/scripts/check_guide_extractor_dependencies.py
backend/scripts/run_test_lanes.py
backend/tests/test_guide_images.py
backend/tests/fixtures/guide_images/**
backend/tests/test_artifact_architecture.py
backend/tests/test_guide_bindings.py
backend/tests/test_guide_extraction.py
backend/tests/test_guide_extractor_dependencies.py
backend/tests/test_guide_formats.py
docs/spec_artifact_storage_service.md
docs/operations_backend_testing.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/**
```

## Not allowed

OCR, pixel/base64 agent input, EXIF secrets/location propagation, transforms,
PDF/OOXML packages, framework/AUTH/Celery/submission changes.

## Acceptance criteria

- Do not edit the approved dependency allowlist. Install `Pillow==12.3.0` only
  through the two exact hash-bound direct wheel URLs already approved by
  03B3B1, using mutually exclusive `python_version == "3.11"` and
  `python_version == "3.12"` markers. Unsupported Python/platform combinations,
  source distributions, alternate indexes, compatible pins, or fallback
  packages fail the dependency gate; no unapproved artifact is resolved.
- Exact 03B2 `png`, `jpeg`, or `webp` classification is required. The isolated
  child independently re-parses the complete payload signature and structural
  header; its detected format and dimensions must agree with Pillow. The child
  receives no trusted classifier facts and never relies on filename or MIME.
- Policy `guide-extraction-v6` emits exactly this compact, sorted JSON object:

  ```json
  {"bit_depth":8,"color_model":"rgb","detected_format":"png","frame_count":1,"height":480,"transparency":false,"width":640}
  ```

  The exact keys are `bit_depth`, `color_model`, `detected_format`,
  `frame_count`, `height`, `transparency`, and `width`. Integers are positive,
  transparency is boolean, detected format is `png|jpeg|webp`, and color model
  is one of `grayscale`, `grayscale_alpha`, `indexed`, `rgb`, `rgba`, `ycbcr`,
  or `cmyk`. No source filename, MIME, pixel sample, text, parser diagnostic, or
  arbitrary metadata key/value is permitted.
- Image omission facts remain exactly `{"truncated":false,"omitted":false}`:
  non-structural metadata is outside the image capability rather than partial
  canonical content. The v6 result is a structural fact and cannot satisfy a
  required textual guide-source item; 03B4 must consume it only as typed image
  metadata and must not concatenate its JSON into textual sufficiency input.
- Parser imports and execution exist only in the isolated extraction child,
  never API, materialization/provider, AUTH, Celery, or agent assembly paths.
- The worker imports the approved adapter before descriptor-only seccomp, as it
  does for other approved parsers. After seccomp, the adapter parses signature,
  dimensions, bit depth/color type, transparency markers, and structural frame
  declarations before `Image.open`, decoder entry, seeking frames, or any
  image-sized allocation. It rejects zero dimensions, either dimension above
  16,384, or pixel product above 40,000,000 first. Pillow decompression-bomb
  warnings/errors are fatal and sanitized.
- PNG semantics come from valid signature/IHDR/chunk structure: color types
  `0,2,3,4,6` normalize respectively to grayscale, rgb, indexed,
  grayscale_alpha, and rgba; bit depth must be valid for that color type;
  alpha color types or a valid `tRNS` marker set transparency. APNG `acTL`
  declares exact frame count. JPEG uses a supported SOF marker: precision must
  be 8, one component is grayscale, three are ycbcr, four are cmyk, frame count
  is one, and transparency is false; baseline/progressive encoding does not
  alter canonical color model. WebP validates RIFF/WEBP and VP8, VP8L, or VP8X
  structure: bit depth is 8, alpha normalizes rgb to rgba, and animation frame
  count comes from validated ANMF structure. Pillow format, size, normalized
  mode/transparency, and `n_frames` must agree with the independent facts.
- Frame count `1..1000` is accepted; zero or conflicting declarations are
  malformed and 1001 fails `limit_exceeded/image_frame_limit` before frame
  iteration or decode. No frame pixels are loaded. A static or animated image
  produces metadata only and never satisfies textual guide semantics.
- Discard EXIF, XMP, IPTC, ICC payloads, PNG text chunks, JPEG comments,
  thumbnails, geolocation, and every other ancillary metadata value. The
  adapter never calls `getexif`, never serializes `Image.info`, and never emits
  raw metadata values. PNG/JPEG/WebP fixtures containing distinct sentinel
  secrets prove none reaches canonical output, omission facts, errors, or
  parent protocol output.
- Stable adapter failures are:

  ```text
  malformed/image_invalid_header
  malformed/image_truncated
  malformed/image_format_mismatch
  malformed/image_decoder_mismatch
  malformed/image_decoder_rejected
  unsupported/image_bit_depth
  unsupported/image_color_model
  limit_exceeded/image_dimension_limit
  limit_exceeded/image_pixel_limit
  limit_exceeded/image_frame_limit
  limit_exceeded/image_decompression_bomb
  ```

  Unexpected native/parser loss remains the existing sanitized
  `parser_failure/parser_failure` or supervisor `parser_failure/executor_lost`;
  wall/CPU/memory/input/output failures retain the existing framework codes.
- Inherit D42's 32 MiB input, 4 MiB output, CPU/wall-clock, address-space,
  descriptor, child/core, termination, and scratch-cleanup rules. Prove these
  resource boundaries plus malformed, truncated, decompression-bomb, 16,384
  accepted/16,385 rejected dimension, 40,000,000 accepted/smallest feasible
  over-limit pixel product, 1000/1001 frame, crash, timeout, cancellation, and
  cleanup outcomes. Because 40,000,001 factors only as `53 * 754717`, it cannot
  isolate the pixel gate while remaining under the 16,384 dimension limit;
  tests assert the exact production constant, a production-feasible first
  over-limit product, and an exact configured-limit/one-over transition.
- Tests prove the real 03B2 classifier and isolated worker agree for every
  format; malformed/truncated and metadata-bearing fixtures cover PNG, JPEG,
  and WebP; child-only imports and v6 persistence/replay are deterministic.
  The dedicated image module belongs to the existing canonical hosted semantic
  lane without changing lane or repository coverage policy.

## Verification commands

```bash
(cd backend && uv run python scripts/check_guide_extractor_dependencies.py)
(cd backend && uv run ruff check app tests scripts)
(cd backend && uv run pytest -q tests/test_guide_images.py --cov=app.modules.artifacts.guide_images --cov-branch --cov-report=term-missing --cov-fail-under=90)
(cd backend && uv run pytest -q tests/test_guide_formats.py tests/test_guide_images.py tests/test_guide_extraction.py tests/test_artifact_architecture.py tests/test_guide_extractor_dependencies.py)
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

Metadata minimization, dimension checks before allocation, decompression-bomb
behavior, and absence of OCR/raw pixels.
