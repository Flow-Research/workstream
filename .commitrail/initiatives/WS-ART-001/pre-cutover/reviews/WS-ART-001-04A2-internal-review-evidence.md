# WS-ART-001-04A2 Internal Review Evidence

## Evidence gate

Result: PASS.

- Scope remains hidden and process-local: no public route, provider I/O,
  durable admission, Submission, checker, semantic manifest, or AUTH activation.
- One outer ZIP is inspected through `PreparedArtifact.inspect(...)` while
  canonical scratch custody remains with `ArtifactScratchManager`.
- Exact envelope and record coverage rejects prefixes, suffixes, gaps,
  overlaps, central-directory disagreement, local/central disagreement,
  descriptor corruption, stored extra bytes, and deflate unused tails.
- Paths, normalized collisions, ancestry conflicts, encryption, special Unix
  entries, directory payloads, expansion ratios, actual bytes, and deadlines
  fail closed with redacted stable internal codes.
- Nested ZIP members remain opaque regular files. Only stored and raw-DEFLATE
  member compression is accepted in v0.1.
- Ruff, focused tests, focused 90-percent subsystem coverage, semantic-lane
  inventory, stale scans, Markdown links, and diff checks pass locally.

## Reviewer results

- Architecture: PASS after startup cross-limit validation and a distinct
  collision failure token were added.
- Security: PASS WITH LOW RISKS after exact byte-envelope/record coverage,
  stored-size equality, and exact deflate consumption were added. Its remaining
  aggregate-budget observation was also resolved during each member read.
- QA: PASS WITH LOW RISKS after exact envelope, hidden directory payload, and
  complete adversarial seam cleanup proofs were added.
- Product/operations: PASS after local filenames for every entry, including
  directories, were bound exactly to the central-directory name.
- Senior engineering: PASS WITH LOW RISKS after the neutral ZIP helper move,
  directory payload rejection, and finite deadline validation.
- CI integrity: PASS WITH LOW RISKS; no workflow, threshold, package-script, or
  dependency weakening. Hosted Backend and Agent Gates remain required.
- Documentation: PASS.
- Reuse/dedup: PASS after the ZIP directory probe moved to neutral
  `zip_safety.py`.
- Test delta: PASS WITH LOW RISKS after all requested adversarial and
  configuration-mapping cases were added.

## Findings resolved

- Safe central names cannot hide unsafe local-header names.
- No byte before, between, inside, or after ZIP records escapes accounting.
- Directory entries cannot carry hidden payloads.
- Stored and deflated members cannot hide bytes beyond logical content.
- ZIP64 is bounded while multi-disk/spanned layouts remain rejected.
- Configuration limits are validated at startup and capped at 512 MiB.

## Residual risk

The behavior has no public caller yet. Hosted PR shards, CodeRabbit, and human
review of the exact commit remain required before merge.
