# WS-ART-001-03B3B4 PR Trust Bundle

## Chunk

`WS-ART-001-03B3B4` — Image Metadata Extractors (L1).

## Goal and human-approved intent

Install only the pre-approved Pillow artifact and add bounded PNG, JPEG, and
WebP structural metadata extraction after exact guide-source classification.
Original verified bytes remain authoritative. This hidden chunk does not add
OCR, raw pixels, AUTH activation, guide sufficiency, submission ZIP handling,
or a second parser/storage path.

## What changed and why

- Added an isolated image adapter that independently validates complete image
  structure before Pillow decoder entry and emits only canonical metadata.
- Advanced supported images to `guide-extraction-v6` through the existing
  extraction worker and immutable persistence/replay path.
- Installed only the approved hash-bound CPython 3.11/3.12 manylinux x86_64
  Pillow wheels and made unsupported Python/platform combinations fail closed.
- Added direct, isolated-worker, architecture, dependency, persistence/replay,
  semantic-lane, and documentation proof for all three formats.

## Design chosen and alternatives rejected

The existing worker loads the approved Pillow plugins before descriptor-only
seccomp, then the image adapter re-parses PNG chunks/CRCs, JPEG SOF structure,
or WebP RIFF structure before `Image.open`. Pillow must agree on format,
dimensions, mode, and frame count. Rejected alternatives were request-path
parsing, trusting MIME/classifier facts, direct provider access, OCR, pixel
loading, metadata propagation, unapproved wheels, and generic download or AUTH
capabilities.

## Scope control and product behavior

Only hidden guide-source extraction changes. Guide source items may be PNG,
JPEG, or WebP; contributor submissions remain one outer ZIP. Image output is
typed structural metadata and cannot satisfy required textual guide semantics.
No route, AUTH action, Celery continuation, agent invocation, submission,
review, contribution, payment, or reputation behavior changes.

## Acceptance criteria proof

- Compact sorted v6 JSON has the exact fixed keys and closed format/color
  enums; omission facts remain exactly non-truncated/non-omitted.
- PNG validates signature, CRC, IHDR, `tRNS`, APNG sequences/count/bounds;
  JPEG validates SOF precision/components; WebP validates RIFF, VP8/VP8L/VP8X,
  alpha, animation headers, frame bounds, and counts before decoder entry.
- Limits cover 16,384 dimensions, 40,000,000 pixels, and 1,000 frames,
  including exact one-over and smallest feasible production pixel cases.
- EXIF, XMP, IPTC, ICC, comments, text chunks, thumbnails, raw pixels, parser
  diagnostics, and sentinels never reach canonical output or error protocol.
- The dependency gate binds exact approved wheel URLs/hashes, requires matching
  runtime declarations, and rejects unsupported Python, OS, architecture, or
  libc facts.

## Tests and checks run

- Dependency gate, `uv lock --check`, Ruff, stale-contract scan, Markdown links,
  and `git diff --check` — pass.
- Image/dependency focused suite — 107 passed; image branch coverage 90.76%.
- Image/extraction/dependency suite with real isolated PNG/JPEG/WebP workers —
  203 passed; image branch coverage 90.76%.
- Format/image/extraction/architecture/dependency integration suite — 247
  passed.
- DB-backed persistence/replay and repository-wide coverage remain assigned to
  hosted Backend/Agent Gates; no local full-suite run was used.

## Test delta and CI integrity

No test, assertion, lane, workflow, or coverage threshold was removed, skipped,
or weakened. All three formats have direct stable-code tests, real isolated
worker tests, and DB persistence/replay parametrization. The image module joins
the existing semantic lane. Hosted Artifact 90 percent and repository 78
percent coverage gates remain unchanged. The large lockfile deletion is
mechanical pruning of Python 3.13+ wheel records after narrowing the supported
backend range to the approved 3.11/3.12 native-wheel matrix.

## Reviewer results

Plan, architecture, security, product/ops, QA, senior engineering, docs,
reuse/dedup, CI integrity, and test-delta reviews pass. Valid findings for PNG transparency,
APNG declaration validation, runtime/platform enforcement, missing runtime
dependency detection, pixel-boundary proof, cross-format isolated/persistence
proof, exact documentation, and lockfile scope were repaired or verified and
re-reviewed.

## External review

The first Agent Gates run found two ambiguous uses of `worker` in the chunk
contract; both were corrected to `extraction child`. CodeRabbit initially
reported its review limit rather than code findings, so a fresh review remains
to be requested. Hosted checks and CodeRabbit supplement but do not replace
internal review, and valid findings must be repaired before human merge.

## Remaining risks and follow-up work

Classifier and child image limits are intentionally independently enforced, so
tests pin their agreement to prevent drift. ART-03B4 must consume v6 image JSON
as typed metadata rather than textual sufficiency input. AUTH activation and
legacy cutover remain later separate chunks.

## Human review focus and merge ownership

Review pre-decoder hostile-container validation, metadata minimization, native
wheel/runtime enforcement, v6 replay identity, and the absence of OCR, raw
pixels, AUTH activation, or sufficiency invocation. A human owns merge
approval; the agent will not merge this PR.
