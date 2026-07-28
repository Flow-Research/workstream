# PR Trust Bundle: WS-ART-001-03A

## Chunk

`WS-ART-001-03A` — Guide Source Byte Ingest (L1)

## Goal And Human-Approved Intent

Accept exact guide-source bytes through bounded private scratch and the existing
immutable ArtifactStore path, without binding or activating guide reads yet.

## What Changed And Why

- Added a hidden guide item artifact route that defaults to concealed denial.
- Added server-owned guide ingest staging facts and migration `0038`.
- Reused preparation, capacity admission, put attempt, verification, ambiguity,
  and recovery paths instead of adding candidate storage.
- Bound final durable effects to one opaque transaction-local AUTH handle and
  exact locked lineage plus server-computed digest, size, and media type.
- Added confirmed-missing replay, downgrade refusal, focused tests, and the
  exact projects subsystem coverage gate.

## Design And Scope Control

Preflight occurs before runtime construction or byte reads. Final PREP consume,
staging, capacity reservation, and put intent commit together. Provider I/O
runs afterward through the already-activated fixed-service put resolver.
Binding, materialization, setup continuation, legacy removal, and guide action
activation remain outside 03A. No provider/factory or public API expansion was
introduced.

## Acceptance Proof

- Server bytes, not caller hashes or provider references, define identity.
- Exact replay reuses the attempt; confirmed absence reacquires released
  capacity before another conditional write.
- Hidden malformed/missing idempotency metadata returns 404 without ingest.
- Populated guide-ingest evidence cannot be destroyed by downgrade.
- Nine internal reviewer tracks pass after all blocking repairs.

## Tests And CI Integrity

Focused route/architecture tests, isolated PostgreSQL migration/admission/replay
tests, changed-file Ruff, compilation, stale-contract/wording/auth scans,
Markdown links, diff checks, and agent gates pass. GitHub owns the full sharded
suite, repository 78% floor, and accumulated 90% subsystem gates; thresholds
were not lowered and the exact projects 90% gate was added. The initial hosted
preflight identified one missing semantic-lane assignment; the bounded repair
and its exact ownership regression pass canonical collection. The next hosted
run executed all lanes and exposed one stale expected-schema fingerprint after
the SHA-256 constraint hardening; the guard now uses the hosted canonical value.
The following run executed 1,618 tests (1,615 pass) and identified three stale
lineage/unit fixtures, now corrected without production changes. The next run
passed all shared/project/task tests and 91/92 schema tests; its sole asyncpg
multi-command seed issue is split into individual transactional statements and
the exact isolated migration proof passes. The subsequent run again passed all
shared/project/task tests and 91/92 schema tests; its sole failure exposed the
human identity-link invariant in the migration fixture. The fixture now creates
the required active, verified identity link, and the exact isolated migration
proof passes. The following hosted run passed all semantic lanes, API E2E, and
repository coverage, then measured the unchanged artifact-foundation gate at
89.77%. Focused production tests now exercise absent/missing/resolved committed
put replay and fail-closed missing PREP transaction behavior; neither production
code nor the 90% threshold changed.

## External Review

CodeRabbit was rate-limited and reported no code findings. GitHub Agent Gates
passed; Backend preflight produced the semantic-lane finding above, which was
repaired and internally re-reviewed before rerun.

## Remaining Risks And Follow-Up

The guide ingest action intentionally remains unavailable. After this PR merges,
AUTH `WS-XINT-002-04A` installs the exact Project Manager adapter and activates
only guide ingestion. ART-03B remains a separate explicit-start successor.

## Human Review Focus And Merge Ownership

Confirm the two authorization points, commit-before-provider boundary,
confirmed-missing replay, and strict 03A scope. The user retains approval and
merge ownership for this specific PR.
