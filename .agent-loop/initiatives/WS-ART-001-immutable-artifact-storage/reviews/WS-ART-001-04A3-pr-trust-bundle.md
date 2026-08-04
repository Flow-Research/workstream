# WS-ART-001-04A3 PR Trust Bundle

## Chunk

`WS-ART-001-04A3 — Semantic Manifest And Change Gate` (L1)

## Goal and human-approved intent

Derive the complete semantic identity of a contributor's one required outer
ZIP and reject exact or semantic unchanged work before checker or provider I/O.
The ZIP contents remain governed by the locked Project Guide. This chunk is a
hidden process-local capability; it does not activate submission preparation.

## What changed and why

- Extended the existing 04A2 full member read to compute each regular file's
  exact SHA-256 and normalized executable intent.
- Added one immutable closed-schema manifest with deterministic canonical JSON
  hashing and self-validation.
- Added a side-effect-free typed predecessor/change gate with stable internal
  failure tokens.
- Added focused semantic, executable, packaging, predecessor, and stale-selector
  tests and registered both new modules in the existing semantic CI lane.
- Tightened the chunk contract and canonical artifact specification to exclude
  legacy caller-owned manifest/package authority.

## Design and boundaries

There is one ZIP traversal: 04A3 derives identity while 04A2 fully validates
and reads each member. Explicit and synthetic parent directories canonicalize
identically; distinct empty directories remain semantic. Nested ZIPs stay
opaque files. Unix execute bits collapse to a boolean; arbitrary permissions
are neither preserved nor executed.

The manifest and gate remain process-local. `04C2` owns durable verified
admission publication and manifest persistence. `05A` owns atomic Submission
binding and predecessor revalidation. Existing caller-supplied package fields
are never read, migrated, or treated as a fallback.

## Acceptance proof

- ZIP order, timestamp, comments, compression, read/write bits, ownership-like
  metadata, and setuid changes do not change semantic identity.
- File bytes, path, type, size, empty-directory presence, and executable intent
  do change semantic identity.
- First submission passes; exact and semantic equality reject distinctly;
  absent canonical predecessor identity and stale/current-selector mismatch
  fail closed.
- Rejection creates no database, checker, provider, lifecycle, contribution,
  compensation, reputation, or review effect.

## Tests and CI integrity

- Focused archive/manifest/change-gate/lane tests: `85 passed`.
- Focused subsystem coverage: `92.11%` with a 90-percent minimum.
- Backend Ruff, stale scans, Markdown links, and diff checks: passed.
- No existing 04A2 test was changed, removed, skipped, or weakened.
- No workflow, package, timeout, lane, or coverage-policy behavior changed.
- Hosted `Backend / test` retains the repository-wide 78-percent floor and the
  existing ART 90-percent gate; `Agent Gates / agent-gates` remains required.

## Reviewer results

All nine required final tracks pass: architecture, security, QA,
product/operations, senior engineering, CI integrity, documentation,
reuse/dedup, and test delta. Security's stale-selector finding was repaired and
covered before final PASS.

## Remaining risk and human review focus

Review the closed manifest schema, executable normalization, server-owned hash
derivation, and required current-predecessor equality. Confirm no legacy
caller-owned package/manifest field or provider/durable/public path is present.
Only the human repository owner may approve and merge after hosted checks and
external review pass.
