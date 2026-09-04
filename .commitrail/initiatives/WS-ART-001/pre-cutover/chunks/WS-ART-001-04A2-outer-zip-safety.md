# Chunk Contract: WS-ART-001-04A2 — Bounded Outer-ZIP Safety

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Implemented; internal review passed

## Goal

Accept one outer ZIP into canonical private scratch and safely enumerate its
complete file/directory tree without provider I/O or a public route.

## Allowed Files

- `backend/app/modules/artifacts/submission_archive.py`: dedicated contributor
  outer-ZIP inspector and closed process-local result/failure types;
- `backend/app/modules/artifacts/zip_safety.py`: neutral bounded ZIP-directory
  facts shared by guide and submission consumers;
- `backend/app/modules/artifacts/guide_formats.py`: import the moved neutral
  `zip_directory_facts()` probe only, without changing guide classification;
- `backend/app/core/config.py` and
  `backend/app/adapters/artifacts/__init__.py`: conservative ZIP-safety settings
  and composition only;
- `backend/tests/test_submission_archive.py`, `backend/tests/test_config.py`,
  and narrowly necessary
  additions to `backend/tests/test_artifact_preparation.py`: adversarial
  inspection, fixed configuration, and scratch cleanup proof;
- `backend/scripts/run_test_lanes.py` and
  `backend/tests/test_ci_test_lanes.py`: exact semantic-lane custody for the
  two new focused modules only;
- this contract, the PLAN3 focused-test mapping, the ART status/chunk map,
  artifact-storage specification, and
  scoped review/coverage evidence; `AUTH_HANDOFF.md` only for current merged
  dependency wording.

## Not Allowed Changes

Semantic manifest/change comparison, project checker, durable admission,
provider I/O, nested archive extraction, larger limits, or AUTH activation.
Do not reuse guide-format archive recursion: contributor backslashes are
rejected before normalization and nested ZIP members remain opaque regular
files. Do not add multipart/request parsing in this hidden chunk.

## Internal Handoff And Limits

04A2 must use the existing `PreparedArtifact.inspect(...)` /
`PreparedArtifactInspector` seam. It returns one immutable, non-durable
`SubmissionArchiveInspectionResult` containing only bounded
`SubmissionArchiveEntry` structural facts (normalized POSIX path, closed entry
type, actual byte count, and bounded archive totals) plus closed redacted
failure codes. It must never expose or retain `ZipInfo`, a reader, scratch path
or handle, raw bytes, provider facts, prepared authorization, semantic hashes,
file hashes, executable normalization, or durable identity.

Neutral bounded EOCD/ZIP64/multi-disk directory probing already present as
`zip_directory_facts()` must be reused or moved to a neutral ART module rather
than copied. The guide detector itself must not be reused because its recursive
nested-archive and backslash-normalization semantics are intentionally
different.

The implementation owns conservative startup-fixed limits for maximum entry
count, normalized path bytes/depth, central-directory bytes, actual bytes per
entry, actual total expanded bytes, compression ratio, and inspection time.
Defaults may not raise the existing 512 MiB source ceiling. Limit configuration
is validated once at startup and is identical for processes sharing scratch.

## Acceptance Criteria

Reject non-ZIP/additional items, traversal/absolute/UNC/backslash/control paths,
symlink/special/encrypted/malformed entries, duplicates/NFC/case-fold
collisions, bombs, and every configured limit breach; nested ZIPs stay opaque;
all outcomes clean scratch and disclose no path/handle.

Path validation also rejects empty, `.` and `..` segments, drive/root forms,
ambiguous trailing dot/space segments, file/directory normalized collisions,
and ancestry conflicts such as a regular file `a` plus `a/b`. Implicit
directories are derived deterministically without becoming duplicate entries.

Every regular-file member is fully bounded-read during inspection. Actual reads,
not central-directory declarations, enforce per-entry/aggregate byte and ratio
limits and verify CRC, truncation, local-header consistency, and malformed data
descriptors. Multi-disk/spanned archives and unsupported ZIP64 structures are
rejected; supported bounded ZIP64 metadata must not weaken any limit. ZIP
metadata is never used to create filesystem entries in this chunk.

Cancellation, timeout, malformed input, and every rejection must close the
archive reader and release the enclosing scratch preparation. Stable internal
failure codes distinguish invalid outer ZIP, unsafe path/type, collision,
encryption, malformed/truncated content, bomb/limit breach, and timeout without
including submitted paths or parser/provider details.
v0.1 accepts stored and raw-DEFLATE members only; other compression methods
fail closed and are not silently delegated to provider or checker code.

## Verification Commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && .venv/bin/python -m pytest -q \
  tests/test_submission_archive.py tests/test_config.py tests/test_guide_formats.py)
(cd backend && .venv/bin/python -m pytest -q tests/test_ci_test_lanes.py)
(cd backend && .venv/bin/python -m pytest \
  tests/test_submission_archive.py \
  --cov=app.modules.artifacts.submission_archive --cov-report=term-missing \
  --cov-fail-under=90)
(cd backend && .venv/bin/python -m pytest \
  tests/test_submission_archive.py tests/test_guide_formats.py \
  --cov=app.modules.artifacts.zip_safety --cov-report=term-missing \
  --cov-fail-under=90)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

The exact PR head must pass hosted `Backend / test` at the repository-wide 78
percent floor and `Agent Gates / agent-gates`. Semantic-lane inventory must
collect the new focused module exactly once; no test, coverage, lint, or
documentation gate may be skipped or weakened.

Focused tests explicitly cover CRC/truncation and declared-size mismatch,
local-header/central-directory disagreement, data descriptors, ZIP64 and
multi-disk markers, central-directory abuse, high entry count and compression
ratio, all path/collision classes, Unix special modes, encrypted entries,
nested-ZIP opacity, cancellation/timeout cleanup, result redaction, and proof
that no provider or durable service is reachable.

## Required Reviewers

Security, architecture, QA, product/ops, senior, CI, docs, reuse, test delta.

## Human Review Focus And Stop Conditions

No unchecked byte may escape scratch and no declared ZIP size is trusted.
