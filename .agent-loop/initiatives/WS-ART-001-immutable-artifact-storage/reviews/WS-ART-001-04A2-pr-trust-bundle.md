# WS-ART-001-04A2 PR Trust Bundle

## Chunk

`WS-ART-001-04A2 — Bounded Outer-ZIP Safety` (L1)

## Goal and human-approved intent

Inspect one contributor outer ZIP completely and safely inside canonical
private scratch, returning only bounded structural facts for the later semantic
manifest chunk. The ZIP's required contents remain governed by the locked
Project Guide. This chunk creates no route, checker, provider write, admission,
or Submission.

## What changed and why

- Added immutable structural result, entry, limit, and redacted failure types.
- Added exact ZIP envelope, central-directory, local-record, descriptor,
  compression-stream, path, collision, type, and quota validation.
- Moved the neutral bounded ZIP directory probe into `zip_safety.py` for guide
  and submission reuse without guide-specific recursion.
- Added startup-fixed settings and composition for outer-ZIP limits.
- Registered the focused test module in the semantic CI lane.
- Updated the ART contract/status and canonical storage specification.

The later manifest, checker, reviewer, and client chain cannot trust a ZIP if
bytes can hide outside its enumerated tree or scratch ownership leaks.

## Design chosen and alternatives rejected

`SubmissionArchiveInspector` implements the existing
`PreparedArtifactInspector` seam. It reads scratch-owned bytes without
extracting them and returns sorted process-local facts only. It accepts stored
and raw-DEFLATE members, treats nested ZIPs as opaque files, and proves
continuous byte coverage through the exact EOCD/comment boundary.

Rejected: guide-detector reuse, recursive nested ZIP inspection, direct temp
paths, a second scratch manager, provider writes, caller-owned limits,
self-extracting envelopes, and compression methods without exact-consumption
proof.

## Scope control and product behavior

No public/multipart route, durable model or migration, provider I/O, AUTH
activation, checker invocation, semantic hash, executable normalization,
unchanged-work comparison, or Submission behavior was added. Hidden inspection
returns a bounded tree or one stable redacted internal failure. Rejection has no
capacity, provider, review, contribution, payment, or reputation effect.

## Acceptance criteria proof

- Every regular member is fully read and CRC-checked through `zipfile`; exact
  stored/deflate range consumption is independently proven.
- Prefixes, suffixes, gaps, overlaps, local/central mismatches, malformed data
  descriptors, multi-disk layouts, traversal, collisions, special entries,
  encryption, directory payloads, and bombs reject.
- Cancellation, timeout, and rejection prove scratch release through
  `PreparedArtifact.inspect(...)`.
- Nested archives remain opaque; results expose no reader, path, bytes,
  provider fact, authorization handle, hash, or durable identity.

## Tests/checks run and test delta

- Repository-wide backend Ruff: passed.
- Focused archive/config/guide/CI-lane tests: passed.
- `submission_archive.py` and `zip_safety.py`: each exceeds 90-percent focused
  coverage.
- Stale artifact/auth/wording scans, Markdown links, and `git diff --check`:
  passed.
- No tests were removed, skipped, or weakened. Semantic lane inventory includes
  the new test module exactly once.

## CI integrity and reviewer results

No workflow, threshold, dependency, package-script, or skip behavior changed.
The repository-wide 78-percent hosted floor and Backend/Agent Gates remain
required. Architecture, product/operations, documentation, and reuse reviews
pass. Security, QA, senior engineering, CI integrity, and test-delta reviews
pass with only documented low residual risks; all actionable findings were
resolved.

## External review

CodeRabbit and hosted GitHub checks have not run yet. Findings must be triaged
against the exact PR head before merge.

## Remaining risks and follow-up

Only stored and raw-DEFLATE ZIP members are supported in v0.1. 04A3 adds the
canonical semantic manifest, executable normalization, and unchanged-work gate
only after this PR merges.

## Human review focus and merge ownership

Review byte-range accounting, local/central name binding, deflate EOF/unused
data, path collisions, and absence of provider/durable/public reachability.
Only the human repository owner may approve and merge after hosted checks and
external review pass.
